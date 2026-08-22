#!/bin/bash
set -e

export AWS_PAGER=""
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export VPC_ID=vpc-026b646e6be12b1b1
export PUB_SUBNET_1=subnet-05ff6291a1b517ec4
export PUB_SUBNET_2=subnet-0851d110729278fdd
export PRIV_SUBNET_1=subnet-0f3b7cb665bc6be18
export PRIV_SUBNET_2=subnet-0d7d407c6ba5175df
export ALB_SG=sg-017ec9d779c1c8bd4
export ECS_SG=sg-0b0b7dc70380cdc56
export ECR_REPO=personal/rag-platform
export DOMAIN_NAME=rag.baynly.com
export CLUSTER_NAME=rag-platform

echo "=========================================="
echo "  RAG Platform: ALB + ECS Deployment"
echo "=========================================="

# ==========================================
# PHASE 3: ECS CLUSTER
# ==========================================
echo ""
echo ">>> Phase 3: ECS Cluster"

EXISTING_CLUSTER=$(aws ecs describe-clusters --clusters $CLUSTER_NAME --query 'clusters[0].clusterName' --output text 2>/dev/null || echo "none")

if [ "$EXISTING_CLUSTER" == "None" ] || [ "$EXISTING_CLUSTER" == "none" ]; then
    aws ecs create-cluster --cluster-name $CLUSTER_NAME \
      --settings name=containerInsights,value=enabled \
      --capacity-providers FARGATE FARGATE_SPOT
    echo "Cluster created: $CLUSTER_NAME"
else
    echo "Cluster exists: $CLUSTER_NAME"
fi

# ==========================================
# PHASE 4: SSL CERTIFICATE
# ==========================================
echo ""
echo ">>> Phase 4: SSL Certificate"

CERT_ARN=$(aws acm list-certificates --query "CertificateSummaryList[?DomainName=='$DOMAIN_NAME'].CertificateArn | [0]" --output text)

if [ "$CERT_ARN" == "None" ] || [ "$CERT_ARN" == "" ]; then
    CERT_ARN=$(aws acm request-certificate \
      --domain-name $DOMAIN_NAME \
      --validation-method DNS \
      --idempotency-token ragapi2026 \
      --query 'CertificateArn' --output text)
    echo "Certificate requested: $CERT_ARN"
    echo ""
    echo "⚠️  ACTION REQUIRED: Add this CNAME record to Hostinger DNS:"
    
    VALIDATION_RECORD=$(aws acm describe-certificate --certificate-arn $CERT_ARN --query 'Certificate.DomainValidationOptions[0].ResourceRecord' --output json)
    CNAME_NAME=$(echo $VALIDATION_RECORD | python3 -c "import sys,json; print(json.load(sys.stdin)['Name'])")
    CNAME_VALUE=$(echo $VALIDATION_RECORD | python3 -c "import sys,json; print(json.load(sys.stdin)['Value'])")
    
    echo "  Name:  $CNAME_NAME"
    echo "  Value: $CNAME_VALUE"
    echo ""
    echo "Then wait for certificate status to become ISSUED:"
    echo "  aws acm describe-certificate --certificate-arn $CERT_ARN --query 'Certificate.Status'"
    echo ""
    echo "Once ISSUED, rerun this script."
    exit 0
else
    CERT_STATUS=$(aws acm describe-certificate --certificate-arn $CERT_ARN --query 'Certificate.Status' --output text)
    echo "Certificate exists: $CERT_ARN (Status: $CERT_STATUS)"
    
    if [ "$CERT_STATUS" != "ISSUED" ]; then
        echo "Certificate not yet ISSUED. Add DNS validation to Hostinger and wait."
        exit 0
    fi
fi

# ==========================================
# PHASE 5: APPLICATION LOAD BALANCER
# ==========================================
echo ""
echo ">>> Phase 5: Application Load Balancer"

# Create Target Group
TG_ARN=$(aws elbv2 create-target-group \
  --name rag-api-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --healthy-threshold-count 2 \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

echo "Target Group created: $TG_ARN"

# Create ALB
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name rag-alb \
  --scheme internet-facing \
  --type application \
  --subnets $PUB_SUBNET_1 $PUB_SUBNET_2 \
  --security-groups $ALB_SG \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN --query 'LoadBalancers[0].DNSName' --output text)

echo "ALB created: $ALB_ARN"
echo "ALB DNS: $ALB_DNS"

# Create HTTPS Listener
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=$CERT_ARN \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN

echo "HTTPS listener created"

# Create HTTP -> HTTPS redirect listener
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'

echo "HTTP redirect listener created"

# ==========================================
# PHASE 6: ECS TASK DEFINITION
# ==========================================
echo ""
echo ">>> Phase 6: ECS Task Definition"

TASK_ROLE_ARN=$(aws iam get-role --role-name ecsTaskRoleRAG --query 'Role.Arn' --output text)
EXECUTION_ROLE_ARN=$(aws iam get-role --role-name ecsTaskExecutionRoleRAG --query 'Role.Arn' --output text)

# Get secret ARN
SECRET_ARN=$(aws secretsmanager describe-secret --secret-id rag-api/prod --query 'ARN' --output text)

cat > task-definition.json << 'EOF'
{
  "family": "rag-api-task",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "EXECUTION_ROLE_ARN",
  "taskRoleArn": "TASK_ROLE_ARN",
  "containerDefinitions": [
    {
      "name": "rag-api",
      "image": "ECR_IMAGE",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "secrets": [
        {
          "name": "OPENAI_API_KEY",
          "valueFrom": "SECRET_ARN:OPENAI_API_KEY::"
        },
        {
          "name": "PINECONE_API_KEY",
          "valueFrom": "SECRET_ARN:PINECONE_API_KEY::"
        }
      ],
      "environment": [
        {
          "name": "ENV",
          "value": "production"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/rag-api",
          "awslogs-region": "AWS_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')\" || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 90
      },
      "essential": true
    }
  ]
}
EOF

# Replace placeholders
sed -i "s|EXECUTION_ROLE_ARN|$EXECUTION_ROLE_ARN|g" task-definition.json
sed -i "s|TASK_ROLE_ARN|$TASK_ROLE_ARN|g" task-definition.json
sed -i "s|ECR_IMAGE|$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest|g" task-definition.json
sed -i "s|SECRET_ARN|$SECRET_ARN|g" task-definition.json
sed -i "s|AWS_REGION|$AWS_REGION|g" task-definition.json

# Create CloudWatch log group
aws logs create-log-group --log-group-name /ecs/rag-api 2>/dev/null || echo "Log group already exists"

# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json

echo "Task definition registered"

# ==========================================
# PHASE 7: ECS SERVICE
# ==========================================
echo ""
echo ">>> Phase 7: ECS Service"

aws ecs create-service \
  --cluster $CLUSTER_NAME \
  --service-name rag-api-service \
  --task-definition rag-api-task \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$PRIV_SUBNET_1,$PRIV_SUBNET_2],securityGroups=[$ECS_SG],assignPublicIp=DISABLED}" \
  --load-balancers targetGroupArn=$TG_ARN,containerName=rag-api,containerPort=8000 \
  --health-check-grace-period-seconds 60

echo "ECS Service created"

# ==========================================
# PHASE 8: AUTO SCALING
# ==========================================
echo ""
echo ">>> Phase 8: Auto Scaling"

# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/$CLUSTER_NAME/rag-api-service \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 5

# Scale out policy
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/$CLUSTER_NAME/rag-api-service \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name rag-api-scale-out \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "PredefinedMetricSpecification": {"PredefinedMetricType": "ECSServiceAverageCPUUtilization"},
    "TargetValue": 70.0,
    "ScaleOutCooldown": 60,
    "ScaleInCooldown": 300
  }'

echo "Auto scaling configured"

# ==========================================
# OUTPUTS
# ==========================================
echo ""
echo "=========================================="
echo "  DEPLOYMENT COMPLETE"
echo "=========================================="
echo "ALB DNS: $ALB_DNS"
echo "Certificate ARN: $CERT_ARN"
echo "Target Group ARN: $TG_ARN"
echo ""
echo "NEXT STEPS:"
echo "1. Add A record in Hostinger DNS:"
echo "   rag.baynly.com -> $ALB_DNS"
echo ""
echo "2. Wait 2-3 minutes for ECS tasks to start"
echo ""
echo "3. Test: curl https://rag.baynly.com/health"
echo "=========================================="