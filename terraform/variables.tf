variable "aws_region" {
  description = "AWS region to deploy resources"
  default     = "us-east-1"
}

variable "app_name" {
  description = "Name of the application"
  default     = "deepgit"
}

variable "container_image" {
  description = "Docker image URI (e.g., ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/deepsearch:latest)"
  type        = string
  default     = ""  # Will use ECR repo output if not provided
}

variable "container_port" {
  description = "Port exposed by the container"
  default     = 7860
}

variable "github_api_key" {
  description = "GitHub API Key (Server-side - Optional if using OAuth)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "groq_api_key" {
  description = "Groq API Key (Optional if using Bedrock)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "llm_provider" {
  description = "LLM Provider (groq or bedrock)"
  default     = "bedrock"
}
