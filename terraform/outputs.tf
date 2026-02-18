output "cluster_name" {
  value       = aws_ecs_cluster.main.name
  description = "ECS Cluster Name"
}

output "service_name" {
  value       = aws_ecs_service.app.name
  description = "ECS Service Name"
}

output "log_group_name" {
  value       = aws_cloudwatch_log_group.ecs_logs.name
  description = "CloudWatch Log Group Name"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.app.repository_url
  description = "ECR Repository URL - use this for container_image variable"
}

output "ecr_repository_name" {
  value       = aws_ecr_repository.app.name
  description = "ECR Repository Name"
}

# Note: Since we are using Fargate with public IP, the IP changes on restart.
# To find the public IP:
# 1. Go to AWS Console -> ECS -> Clusters -> deepsearch-cluster -> Tasks
# 2. Click the task -> view in CloudWatch logs
# 3. Or use: aws ecs describe-tasks --cluster deepsearch-cluster --tasks <TASK_ARN>
