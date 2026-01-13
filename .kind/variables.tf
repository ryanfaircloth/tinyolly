variable "strimzi_cluster_instance_version" {
  description = "Version of the tinyolly-instance Helm chart"
  type        = string
  default     = "*"
}

variable "gateway_dns_suffix" {
  description = "DNS suffix for gateway routes"
  type        = string
  default     = "tinyolly.test"
}

variable "bootstrap" {
  description = "Bootstrap mode - true for initial cluster creation (no HTTPRoutes), false for subsequent runs"
  type        = bool
  default     = false
}

# Demo application settings
variable "custom_demo_frontend_image" {
  description = "Custom demo frontend image repository (unified demo image)"
  type        = string
  default     = "docker-registry.registry.svc.cluster.local:5000/tinyolly/demo"
}

variable "custom_demo_frontend_tag" {
  description = "Custom demo frontend image tag"
  type        = string
  default     = "latest"
}

variable "custom_demo_backend_image" {
  description = "Custom demo backend image repository (unified demo image)"
  type        = string
  default     = "docker-registry.registry.svc.cluster.local:5000/tinyolly/demo"
}

variable "custom_demo_backend_tag" {
  description = "Custom demo backend image tag"
  type        = string
  default     = "latest"
}
