@echo off
REM Deploy script for DeepSearch to AWS ECS with Terraform (Windows)

setlocal enabledelayedexpansion

echo ======================================
echo DeepSearch AWS ECS Deployment Script
echo ======================================
echo.

REM Check prerequisites
echo Checking prerequisites...

where aws >nul 2>nul
if errorlevel 1 (
    echo ERROR: AWS CLI is not installed
    echo Download from: https://aws.amazon.com/cli/
    exit /b 1
)

where terraform >nul 2>nul
if errorlevel 1 (
    echo ERROR: Terraform is not installed
    echo Download from: https://www.terraform.io/downloads.html
    exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
    echo ERROR: Docker is not installed
    echo Download from: https://docs.docker.com/desktop/install/windows-install/
    exit /b 1
)

echo OK: All prerequisites found
echo.

REM Get AWS Account ID and validate credentials
echo Getting AWS Account ID...
for /f "tokens=*" %%i in ('aws sts get-caller-identity --query Account --output text 2^>nul') do set AWS_ACCOUNT_ID=%%i

if "%AWS_ACCOUNT_ID%"=="" (
    echo ERROR: AWS credentials not configured or invalid
    echo Please run: aws configure
    exit /b 1
)

REM Set region - respect AWS_DEFAULT_REGION, fallback to us-east-1
if "%AWS_DEFAULT_REGION%"=="" (
    set AWS_REGION=us-east-1
) else (
    set AWS_REGION=%AWS_DEFAULT_REGION%
)

set APP_NAME=deepsearch

echo AWS Account ID: %AWS_ACCOUNT_ID%
echo AWS Region: %AWS_REGION%
echo App Name: %APP_NAME%
echo.

REM Set Terraform environment variables for secrets (safer than CLI flags)
echo Setting up environment variables for Terraform...
if "%GITHUB_API_KEY%"=="" (
    echo WARNING: GITHUB_API_KEY not set. Container may fail at runtime.
) else (
    set TF_VAR_github_api_key=%GITHUB_API_KEY%
)

if "%GROQ_API_KEY%"=="" (
    echo WARNING: GROQ_API_KEY not set. Will use bedrock provider.
) else (
    set TF_VAR_groq_api_key=%GROQ_API_KEY%
)
echo.

REM Step 1: Build Docker Image
echo Step 1: Building Docker image...
docker build -t %APP_NAME%:latest .
if errorlevel 1 (
    echo ERROR: Docker build failed
    exit /b 1
)
echo OK: Docker image built
echo.

REM Step 2: Check if ECR repository exists, if not create it
echo Step 2: Checking ECR repository...
aws ecr describe-repositories --repository-names %APP_NAME% --region %AWS_REGION% >nul 2>nul
if errorlevel 1 (
    echo ECR repository does not exist. Creating...
    aws ecr create-repository --repository-name %APP_NAME% --region %AWS_REGION%
    if errorlevel 1 (
        echo ERROR: Failed to create ECR repository
        exit /b 1
    )
    echo OK: ECR repository created
) else (
    echo OK: ECR repository exists
)
echo.

REM Step 3: Authenticate with ECR
echo Step 3: Authenticating with ECR...
for /f "tokens=*" %%i in ('aws ecr get-login-password --region %AWS_REGION% 2^>nul') do (
    echo %%i | docker login --username AWS --password-stdin %AWS_ACCOUNT_ID%.dkr.ecr.%AWS_REGION%.amazonaws.com
)
if errorlevel 1 (
    echo ERROR: ECR authentication failed
    exit /b 1
)
echo OK: ECR authentication successful
echo.

REM Step 4: Tag and Push to ECR
set ECR_REPO_URL=%AWS_ACCOUNT_ID%.dkr.ecr.%AWS_REGION%.amazonaws.com/%APP_NAME%:latest

echo Step 4: Pushing image to ECR...
echo ECR URL: %ECR_REPO_URL%
docker tag %APP_NAME%:latest %ECR_REPO_URL%
docker push %ECR_REPO_URL%
if errorlevel 1 (
    echo ERROR: Docker push failed
    exit /b 1
)
echo OK: Image pushed to ECR
echo.

REM Step 5: Initialize Terraform
echo Step 5: Initializing Terraform...
cd terraform
terraform init
if errorlevel 1 (
    echo ERROR: Terraform init failed
    exit /b 1
)
echo OK: Terraform initialized
echo.

REM Step 6: Plan (secrets come from TF_VAR_* environment variables, not CLI)
echo Step 6: Creating Terraform plan...
terraform plan ^
  -var="aws_region=%AWS_REGION%" ^
  -var="app_name=%APP_NAME%" ^
  -var="container_image=%ECR_REPO_URL%" ^
  -out=tfplan

if errorlevel 1 (
    echo ERROR: Terraform plan failed
    cd ..
    exit /b 1
)
echo OK: Plan created
echo.

REM Step 7: Ask for confirmation
echo Review the plan above. Do you want to apply it? (yes/no)
set /p CONFIRM=
if /i not "%CONFIRM%"=="yes" (
    echo Deployment cancelled
    cd ..
    exit /b 0
)

REM Step 8: Apply
echo Step 8: Applying Terraform configuration...
terraform apply tfplan
if errorlevel 1 (
    echo ERROR: Terraform apply failed
    cd ..
    exit /b 1
)
echo OK: Infrastructure deployed
echo.

REM Step 9: Display outputs (only on success)
echo Deployment Complete!
echo.
echo Outputs:
terraform output -json
echo.

REM Get cluster and task info
for /f "tokens=*" %%i in ('terraform output -raw cluster_name 2^>nul') do set CLUSTER_NAME=%%i
for /f "tokens=*" %%i in ('terraform output -raw service_name 2^>nul') do set SERVICE_NAME=%%i

echo.
echo To find your running tasks and their public IP:
echo aws ecs list-tasks --cluster %CLUSTER_NAME% --region %AWS_REGION%
echo.
echo To view logs:
echo aws logs tail /ecs/%APP_NAME% --follow --region %AWS_REGION%
echo.
cd ..
echo Deployment script completed successfully!
