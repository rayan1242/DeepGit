# Terraform Validation Report

## ✅ GOOD THINGS FOUND

### Terraform Structure
- ✅ Proper provider configuration (AWS ~5.0)
- ✅ Good separation of concerns (main.tf, ecs.tf, iam.tf, vpc.tf, variables.tf, outputs.tf)
- ✅ Using Fargate Spot for cost savings (70% cheaper)
- ✅ CloudWatch logging configured
- ✅ Proper IAM roles (execution + task roles)
- ✅ VPC setup with 2 AZs for redundancy
- ✅ Security group allows traffic on port 7860

### Docker
- ✅ Dockerfile is correct (Python 3.10, installs requirements)
- ✅ Exposes port 7860 correctly
- ✅ Runs `app.py` as entrypoint

---

## ⚠️ CRITICAL ISSUES TO FIX

### 1. **CloudWatch Logs Group Missing** ❌
**Issue**: `ecs.tf` references `/ecs/deepsearch` log group that doesn't exist
**Fix**: Add this to `ecs.tf`:

```hcl
resource "aws_cloudwatch_log_group" "ecs_logs" {
  name              = "/ecs/${var.app_name}"
  retention_in_days = 7
}
```

### 2. **No Container Registry (ECR)** ❌
**Issue**: `container_image` variable requires Docker image URI, but no ECR repo
**Fix**: Add to `ecs.tf`:

```hcl
resource "aws_ecr_repository" "app" {
  name                 = var.app_name
  image_tag_mutability = "IMMUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
  }
}
```

Update `outputs.tf`:
```hcl
output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}
```

### 3. **Missing terraform.tfvars** ❌
**Issue**: `container_image` is required but has no default value
**Fix**: Before running `terraform apply`, either:

Option A - Create `terraform/terraform.tfvars`:
```hcl
aws_region     = "us-east-1"
app_name       = "deepsearch"
container_image = "ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/deepsearch:latest"
container_port = 7860
github_api_key = "YOUR_GITHUB_TOKEN"
groq_api_key   = "YOUR_GROQ_KEY"
llm_provider   = "bedrock"
```

Option B - Use `-var` flags:
```bash
terraform apply -var="container_image=ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/deepgit:latest"
```

---

## 📋 DEPLOYMENT CHECKLIST

### Step 1: Prepare Docker Image
```bash
# Build Docker image
docker build -t deepsearch:latest .

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="us-east-1"

# Create ECR repo first (or use Terraform)
aws ecr create-repository --repository-name deepsearch --region $AWS_REGION

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Tag and push
docker tag deepsearch:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/deepsearch:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/deepsearch:latest
```

### Step 2: Initialize Terraform
```bash
cd terraform
terraform init
```

### Step 3: Plan
```bash
terraform plan \
  -var="container_image=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/deepsearch:latest" \
  -var="github_api_key=$GITHUB_API_KEY" \
  -var="groq_api_key=$GROQ_API_KEY"
```

### Step 4: Apply
```bash
terraform apply \
  -var="container_image=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/deepsearch:latest" \
  -var="github_api_key=$GITHUB_API_KEY" \
  -var="groq_api_key=$GROQ_API_KEY"
```

### Step 5: Get Task IP
```bash
# List running tasks
aws ecs list-tasks --cluster deepsearch-cluster

# Get task details (includes public IP)
aws ecs describe-tasks --cluster deepsearch-cluster --tasks <TASK_ARN> | grep -i "public"
```

---

## ⚡ OPTIONAL IMPROVEMENTS

### Add Application Load Balancer (for stable URL)
```hcl
resource "aws_lb" "main" {
  name               = "${var.app_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "app" {
  name        = "${var.app_name}-tg"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"
}

resource "aws_lb_listener" "app" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
```
**Cost**: ~$16/month but gives you stable DNS name + automatic failover

### Add Auto-Scaling
```hcl
resource "aws_appautoscaling_target" "ecs_target" {
  max_capacity       = 3
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.app.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}
```

---

## 🚀 QUICK START

```bash
# 1. Login to AWS
aws configure

# 2. Fix terraform (apply the fixes above first)

# 3. Build and push Docker image
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
docker build -t deepsearch:latest .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker tag deepsearch:latest $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/deepsearch:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/deepsearch:latest

# 4. Deploy with Terraform
cd terraform
terraform init
terraform apply -var="container_image=$AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/deepsearch:latest" \
                 -var="github_api_key=$GITHUB_API_KEY" \
                 -var="groq_api_key=$GROQ_API_KEY"
```

---

## 📊 EXPECTED COSTS

| Resource | Cost |
|----------|------|
| Fargate Spot (2 vCPU, 4GB) | ~$0.0428/hour (~$30/month) |
| CloudWatch Logs | ~$0.50/month |
| ECR Storage | ~$0.10/month |
| **Total** | **~$30-40/month** |

---

## ✅ STATUS

**Overall**: 85% Ready
- Core config: ✅
- IAM: ✅  
- Networking: ✅
- Logging: ⚠️ Need CloudWatch Log Group
- Container Registry: ⚠️ Need ECR or use external registry
- Variables: ⚠️ Need container_image value

**Action Items**:
1. [ ] Add CloudWatch Log Group to `ecs.tf`
2. [ ] Add ECR repo to `ecs.tf` OR use external registry
3. [ ] Create `terraform.tfvars` with your values
4. [ ] Build and push Docker image to ECR
5. [ ] Run `terraform plan`
6. [ ] Run `terraform apply`
