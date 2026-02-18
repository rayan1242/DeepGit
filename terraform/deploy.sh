#!/bin/bash
# Deploy script for DeepSearch to AWS ECS with Terraform

set -e

echo "======================================"
echo "DeepSearch AWS ECS Deployment Script"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}ERROR: AWS CLI is not installed${NC}"
    exit 1
fi

if ! command -v terraform &> /dev/null; then
    echo -e "${RED}ERROR: Terraform is not installed${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites found${NC}"
echo ""

# Get AWS Account ID and validate credentials
echo "Getting AWS Account ID..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)

if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}ERROR: AWS credentials not configured or invalid${NC}"
    echo "Please run: aws configure"
    exit 1
fi

# Set region - respect AWS_DEFAULT_REGION, fallback to us-east-1
AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
APP_NAME="${APP_NAME:-deepsearch}"

echo "AWS Account ID: $AWS_ACCOUNT_ID"
echo "AWS Region: $AWS_REGION"
echo "App Name: $APP_NAME"
echo ""

# Set Terraform environment variables for secrets (safer than CLI flags)
echo -e "${YELLOW}Setting up environment variables for Terraform...${NC}"
if [ -z "$GITHUB_API_KEY" ]; then
    echo -e "${YELLOW}WARNING: GITHUB_API_KEY not set. Container may fail at runtime.${NC}"
else
    export TF_VAR_github_api_key=$GITHUB_API_KEY
fi

if [ -z "$GROQ_API_KEY" ]; then
    echo -e "${YELLOW}WARNING: GROQ_API_KEY not set. Will use bedrock provider.${NC}"
else
    export TF_VAR_groq_api_key=$GROQ_API_KEY
fi
echo ""

# Step 1: Build Docker Image
echo -e "${YELLOW}Step 1: Building Docker image...${NC}"
docker build -t $APP_NAME:latest .
echo -e "${GREEN}✓ Docker image built${NC}"
echo ""

# Step 2: Check if ECR repository exists, if not create it
echo -e "${YELLOW}Step 2: Checking ECR repository...${NC}"
if aws ecr describe-repositories --repository-names $APP_NAME --region $AWS_REGION &>/dev/null; then
    echo -e "${GREEN}✓ ECR repository exists${NC}"
else
    echo "ECR repository does not exist. Creating..."
    aws ecr create-repository --repository-name $APP_NAME --region $AWS_REGION
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to create ECR repository${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ ECR repository created${NC}"
fi
echo ""

# Step 3: Authenticate with ECR
echo -e "${YELLOW}Step 3: Authenticating with ECR...${NC}"
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
echo -e "${GREEN}✓ ECR authentication successful${NC}"
echo ""

# Step 4: Tag and Push to ECR
ECR_REPO_URL="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP_NAME:latest"
echo -e "${YELLOW}Step 4: Pushing image to ECR...${NC}"
echo "ECR URL: $ECR_REPO_URL"
docker tag $APP_NAME:latest $ECR_REPO_URL
docker push $ECR_REPO_URL
echo -e "${GREEN}✓ Image pushed to ECR${NC}"
echo ""

# Step 5: Initialize Terraform
echo -e "${YELLOW}Step 5: Initializing Terraform...${NC}"
cd terraform
terraform init
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Terraform init failed${NC}"
    cd ..
    exit 1
fi
echo -e "${GREEN}✓ Terraform initialized${NC}"
echo ""

# Step 6: Plan (secrets come from TF_VAR_* environment variables, not CLI)
echo -e "${YELLOW}Step 6: Creating Terraform plan...${NC}"
terraform plan \
  -var="aws_region=$AWS_REGION" \
  -var="app_name=$APP_NAME" \
  -var="container_image=$ECR_REPO_URL" \
  -out=tfplan

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Terraform plan failed${NC}"
    cd ..
    exit 1
fi
echo -e "${GREEN}✓ Plan created${NC}"
echo ""

# Step 7: Ask for confirmation
echo -e "${YELLOW}Review the plan above. Do you want to apply it? (yes/no)${NC}"
read -r CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Deployment cancelled"
    cd ..
    exit 0
fi

# Step 8: Apply
echo -e "${YELLOW}Step 8: Applying Terraform configuration...${NC}"
terraform apply tfplan
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Terraform apply failed${NC}"
    cd ..
    exit 1
fi
echo -e "${GREEN}✓ Infrastructure deployed${NC}"
echo ""

# Step 9: Display outputs (only on success)
echo -e "${GREEN}Deployment Complete!${NC}"
echo ""
echo "Outputs:"
terraform output -json
echo ""

# Get cluster and task info
CLUSTER_NAME=$(terraform output -raw cluster_name 2>/dev/null)
SERVICE_NAME=$(terraform output -raw service_name 2>/dev/null)

echo -e "${YELLOW}To find your running tasks and their public IP:${NC}"
echo "aws ecs list-tasks --cluster $CLUSTER_NAME --region $AWS_REGION"
echo ""
echo "To view logs:"
echo "aws logs tail /ecs/$APP_NAME --follow --region $AWS_REGION"
echo ""
cd ..
echo -e "${GREEN}Deployment script completed successfully!${NC}"
