#!/bin/bash
set -e

echo "=========================================="
echo "  RAG Platform AWS Deployment Script"
echo "=========================================="

export AWS_PAGER=""
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export VPC_NAME=rag-platform-vpc
export DOMAIN_NAME=rag.baynly.com
export CLUSTER_NAME=rag-platform

echo "AWS Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"

# ==========================================
# PHASE 1: ECR LOGIN (skip if already pushed)
# ==========================================
echo ""
echo ">>> Phase 1: ECR Login (skipping Docker - already pushed)"
# aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
echo "Skipped - image already in ECR"

# ==========================================
# PHASE 2: VPC & NETWORKING (check each resource individually)
# ==========================================
echo ""
echo ">>> Phase 2: Creating VPC and Networking"

# Check VPC
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=$VPC_NAME" --query 'Vpcs[0].VpcId' --output text 2>/dev/null || echo "none")
if [ "$VPC_ID" == "None" ] || [ "$VPC_ID" == "none" ]; then
    echo "Creating VPC..."
    VPC_ID=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=$VPC_NAME}]" --query 'Vpc.VpcId' --output text)
    aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames
    aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-support
    echo "VPC created: $VPC_ID"
    VPC_JUST_CREATED=true
else
    echo "VPC exists: $VPC_ID"
    VPC_JUST_CREATED=false
fi

# Get AZs (always needed)
AZ1=$(aws ec2 describe-availability-zones --region $AWS_REGION --query 'AvailabilityZones[0].ZoneName' --output text)
AZ2=$(aws ec2 describe-availability-zones --region $AWS_REGION --query 'AvailabilityZones[1].ZoneName' --output text)

# Check/Create Public Subnet 1
PUB_SUBNET_1=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=rag-public-1" --query 'Subnets[0].SubnetId' --output text 2>/dev/null || echo "none")
if [ "$PUB_SUBNET_1" == "None" ] || [ "$PUB_SUBNET_1" == "none" ]; then
    echo "Creating public subnet 1..."
    PUB_SUBNET_1=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.1.0/24 --availability-zone $AZ1 --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=rag-public-1}]" --query 'Subnet.SubnetId' --output text)
fi
echo "Public subnet 1: $PUB_SUBNET_1"

# Check/Create Public Subnet 2
PUB_SUBNET_2=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=rag-public-2" --query 'Subnets[0].SubnetId' --output text 2>/dev/null || echo "none")
if [ "$PUB_SUBNET_2" == "None" ] || [ "$PUB_SUBNET_2" == "none" ]; then
    echo "Creating public subnet 2..."
    PUB_SUBNET_2=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.2.0/24 --availability-zone $AZ2 --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=rag-public-2}]" --query 'Subnet.SubnetId' --output text)
fi
echo "Public subnet 2: $PUB_SUBNET_2"

# Check/Create Private Subnet 1
PRIV_SUBNET_1=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=rag-private-1" --query 'Subnets[0].SubnetId' --output text 2>/dev/null || echo "none")
if [ "$PRIV_SUBNET_1" == "None" ] || [ "$PRIV_SUBNET_1" == "none" ]; then
    echo "Creating private subnet 1..."
    PRIV_SUBNET_1=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.3.0/24 --availability-zone $AZ1 --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=rag-private-1}]" --query 'Subnet.SubnetId' --output text)
fi
echo "Private subnet 1: $PRIV_SUBNET_1"

# Check/Create Private Subnet 2
PRIV_SUBNET_2=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=rag-private-2" --query 'Subnets[0].SubnetId' --output text 2>/dev/null || echo "none")
if [ "$PRIV_SUBNET_2" == "None" ] || [ "$PRIV_SUBNET_2" == "none" ]; then
    echo "Creating private subnet 2..."
    PRIV_SUBNET_2=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.4.0/24 --availability-zone $AZ2 --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=rag-private-2}]" --query 'Subnet.SubnetId' --output text)
fi
echo "Private subnet 2: $PRIV_SUBNET_2"

# Check/Create Internet Gateway
IGW=$(aws ec2 describe-internet-gateways --filters "Name=attachment.vpc-id,Values=$VPC_ID" --query 'InternetGateways[0].InternetGatewayId' --output text 2>/dev/null || echo "none")
if [ "$IGW" == "None" ] || [ "$IGW" == "none" ]; then
    echo "Creating internet gateway..."
    IGW=$(aws ec2 create-internet-gateway --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=rag-igw}]" --query 'InternetGateway.InternetGatewayId' --output text)
    aws ec2 attach-internet-gateway --internet-gateway-id $IGW --vpc-id $VPC_ID
fi
echo "Internet Gateway: $IGW"

# Check/Create NAT Gateway (only if private subnets exist and need outbound)
NAT_GW=$(aws ec2 describe-nat-gateways --filter "Name=vpc-id,Values=$VPC_ID" --query 'NatGateways[?State==`available`].NatGatewayId | [0]' --output text 2>/dev/null || echo "none")
if [ "$NAT_GW" == "None" ] || [ "$NAT_GW" == "none" ]; then
    echo "Creating NAT Gateway..."
    EIP=$(aws ec2 allocate-address --domain vpc --query 'AllocationId' --output text)
    NAT_GW=$(aws ec2 create-nat-gateway --subnet-id $PUB_SUBNET_1 --allocation-id $EIP --tag-specifications "ResourceType=natgateway,Tags=[{Key=Name,Value=rag-nat}]" --query 'NatGateway.NatGatewayId' --output text)
    echo "Waiting for NAT Gateway to be available (~2 minutes)..."
    aws ec2 wait nat-gateway-available --nat-gateway-ids $NAT_GW
else
    echo "NAT Gateway exists: $NAT_GW"
fi

# Check/Create Route Tables and Routes
PUB_RT=$(aws ec2 describe-route-tables --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=rag-public-rt" --query 'RouteTables[0].RouteTableId' --output text 2>/dev/null || echo "none")
if [ "$PUB_RT" == "None" ] || [ "$PUB_RT" == "none" ]; then
    echo "Creating public route table..."
    PUB_RT=$(aws ec2 create-route-table --vpc-id $VPC_ID --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=rag-public-rt}]" --query 'RouteTable.RouteTableId' --output text)
    aws ec2 create-route --route-table-id $PUB_RT --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW
    aws ec2 associate-route-table --route-table-id $PUB_RT --subnet-id $PUB_SUBNET_1
    aws ec2 associate-route-table --route-table-id $PUB_RT --subnet-id $PUB_SUBNET_2
fi

PRIV_RT=$(aws ec2 describe-route-tables --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=rag-private-rt" --query 'RouteTables[0].RouteTableId' --output text 2>/dev/null || echo "none")
if [ "$PRIV_RT" == "None" ] || [ "$PRIV_RT" == "none" ]; then
    echo "Creating private route table..."
    PRIV_RT=$(aws ec2 create-route-table --vpc-id $VPC_ID --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=rag-private-rt}]" --query 'RouteTable.RouteTableId' --output text)
    aws ec2 create-route --route-table-id $PRIV_RT --destination-cidr-block 0.0.0.0/0 --nat-gateway-id $NAT_GW
    aws ec2 associate-route-table --route-table-id $PRIV_RT --subnet-id $PRIV_SUBNET_1
    aws ec2 associate-route-table --route-table-id $PRIV_RT --subnet-id $PRIV_SUBNET_2
fi

# Check/Create Security Groups
ALB_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=rag-alb-sg" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "none")
if [ "$ALB_SG" == "None" ] || [ "$ALB_SG" == "none" ]; then
    echo "Creating ALB security group..."
    ALB_SG=$(aws ec2 create-security-group --group-name rag-alb-sg --description "ALB security group" --vpc-id $VPC_ID --query 'GroupId' --output text)
    aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0
    aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0
fi
echo "ALB Security Group: $ALB_SG"

ECS_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=rag-ecs-sg" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "none")
if [ "$ECS_SG" == "None" ] || [ "$ECS_SG" == "none" ]; then
    echo "Creating ECS security group..."
    ECS_SG=$(aws ec2 create-security-group --group-name rag-ecs-sg --description "ECS tasks security group" --vpc-id $VPC_ID --query 'GroupId' --output text)
    aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8000 --source-group $ALB_SG
fi
echo "ECS Security Group: $ECS_SG"

# ==========================================
# PHASE 3: ECS CLUSTER
# ==========================================
echo ""
echo ">>> Phase 3: ECS Cluster"

EXISTING_CLUSTER=$(aws ecs describe-clusters --clusters $CLUSTER_NAME --query 'clusters[0].clusterName' --output text 2>/dev/null || echo "none")
if [ "$EXISTING_CLUSTER" == "None" ] || [ "$EXISTING_CLUSTER" == "none" ]; then
    aws ecs create-cluster --cluster-name $CLUSTER_NAME --settings name=containerInsights,value=enabled --capacity-providers FARGATE FARGATE_SPOT
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
    CERT_ARN=$(aws acm request-certificate --domain-name $DOMAIN_NAME --validation-method DNS --idempotency-token rag-api-2026 --query 'CertificateArn' --output text)
    echo "Certificate requested: $CERT_ARN"
    echo "⚠️  IMPORTANT: Add the DNS validation CNAME to Hostinger!"
else
    echo "Certificate exists: $CERT_ARN"
fi

# ==========================================
# SAVE OUTPUTS
# ==========================================
echo ""
echo "=========================================="
echo "  DEPLOYMENT IDs (SAVE THESE)"
echo "=========================================="
echo "VPC_ID=$VPC_ID"
echo "PUB_SUBNET_1=$PUB_SUBNET_1"
echo "PUB_SUBNET_2=$PUB_SUBNET_2"
echo "PRIV_SUBNET_1=$PRIV_SUBNET_1"
echo "PRIV_SUBNET_2=$PRIV_SUBNET_2"
echo "ALB_SG=$ALB_SG"
echo "ECS_SG=$ECS_SG"
echo "CERT_ARN=$CERT_ARN"
echo "=========================================="

echo ""
echo "✅ Phases 1-4 complete!"
echo ""
echo "NEXT STEPS:"
echo "1. If new certificate, get validation CNAME:"
echo "   aws acm describe-certificate --certificate-arn $CERT_ARN --query 'Certificate.DomainValidationOptions[0].ResourceRecord'"
echo ""
echo "2. Add CNAME to Hostinger DNS"
echo ""
echo "3. Verify certificate status:"
echo "   aws acm describe-certificate --certificate-arn $CERT_ARN --query 'Certificate.Status'"