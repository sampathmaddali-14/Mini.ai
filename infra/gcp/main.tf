# Mini.ai — GCP infrastructure (Terraform)
# One-command bootstrap of the Mini.ai environment.
#
#   terraform init
#   terraform apply -var project_id=my-gcp-project -var region=europe-west2

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# ----------------------------- Variables -----------------------------

variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  default     = "europe-west2"
  description = "Region (europe-west2 = London)"
}

variable "zone" {
  type        = string
  default     = "europe-west2-a"
}

variable "vm_name" {
  type    = string
  default = "mini-ai"
}

variable "vm_machine_type" {
  type    = string
  default = "e2-standard-4"
}

variable "vm_disk_size_gb" {
  type    = number
  default = 200
}

variable "anthropic_api_key" {
  type        = string
  sensitive   = true
  description = "Stored in Secret Manager. Do not commit."
}

# ----------------------------- APIs -----------------------------

resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "storage.googleapis.com",
    "cloudscheduler.googleapis.com",
  ])
  service                    = each.key
  disable_on_destroy         = false
}

# ----------------------------- Service account -----------------------------

resource "google_service_account" "mini_sa" {
  account_id   = "mini-ai-sa"
  display_name = "Mini.ai VM service account"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "sa_secret_reader" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.mini_sa.email}"
}

resource "google_project_iam_member" "sa_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.mini_sa.email}"
}

resource "google_project_iam_member" "sa_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.mini_sa.email}"
}

resource "google_storage_bucket_iam_member" "sa_backup_writer" {
  bucket = google_storage_bucket.backups.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.mini_sa.email}"
}

# ----------------------------- Secrets -----------------------------

resource "google_secret_manager_secret" "anthropic_key" {
  secret_id = "mini-ai-anthropic-api-key"
  replication { auto {} }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "anthropic_key_v1" {
  secret      = google_secret_manager_secret.anthropic_key.id
  secret_data = var.anthropic_api_key
}

# ----------------------------- Artifact Registry -----------------------------

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "mini-ai"
  description   = "Private container images for Mini.ai"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# ----------------------------- Storage (backups) -----------------------------

resource "google_storage_bucket" "backups" {
  name                        = "${var.project_id}-mini-ai-backups"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  versioning { enabled = true }

  lifecycle_rule {
    condition { age = 30 }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
  lifecycle_rule {
    condition { age = 180 }
    action { type = "Delete" }
  }
  depends_on = [google_project_service.apis]
}

# ----------------------------- Networking -----------------------------

# Deny all ingress by default; only allow IAP TCP forwarding for SSH + services
resource "google_compute_firewall" "allow_iap" {
  name    = "mini-ai-allow-iap"
  network = "default"
  allow {
    protocol = "tcp"
    ports    = ["22", "7090"]
  }
  # Google's IAP TCP forwarding address range
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["mini-ai"]
}

# ----------------------------- Compute VM -----------------------------

resource "google_compute_instance" "mini_ai" {
  name         = var.vm_name
  machine_type = var.vm_machine_type
  zone         = var.zone
  tags         = ["mini-ai"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.vm_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"
    # No access_config block = no public IP
  }

  service_account {
    email  = google_service_account.mini_sa.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = file("${path.module}/startup.sh")

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.anthropic_key_v1,
  ]
}

# ----------------------------- Outputs -----------------------------

output "vm_name" {
  value = google_compute_instance.mini_ai.name
}

output "vm_internal_ip" {
  value = google_compute_instance.mini_ai.network_interface[0].network_ip
}

output "backup_bucket" {
  value = google_storage_bucket.backups.name
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "iap_tunnel_cmd" {
  value = "gcloud compute start-iap-tunnel ${google_compute_instance.mini_ai.name} 7090 --local-host-port=localhost:7090 --zone=${var.zone}"
}
