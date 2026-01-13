
variable "gateway_dns_suffix" {
  description = "DNS suffix for gateway routes"
  type        = string
}

variable "custom_demo_frontend_image" {
  description = "Custom demo frontend image"
  type        = string
  default     = "ghcr.io/ryanfaircloth/tinyolly-demo-frontend"
}

variable "custom_demo_frontend_tag" {
  description = "Custom demo frontend tag"
  type        = string
  default     = "latest"
}

variable "custom_demo_backend_image" {
  description = "Custom demo backend image"
  type        = string
  default     = "ghcr.io/ryanfaircloth/tinyolly-demo-backend"
}

variable "custom_demo_backend_tag" {
  description = "Custom demo backend tag"
  type        = string
  default     = "latest"
}
