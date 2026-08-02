@echo off
set POLICY_NAME=AI-Power-User-Policy
set GROUP_NAME=AI-Engineers
set USER_NAME=Salah-Default

echo Creating custom policy...
aws iam create-policy --policy-name %POLICY_NAME% --policy-document file://ai-power-user-policy.json

echo Creating group...
aws iam create-group --group-name %GROUP_NAME%

echo Attaching custom policy to group...
for /f "tokens=*" %%a in ('aws iam create-policy --policy-name %POLICY_NAME% --policy-document file://ai-power-user-policy.json --query "Policy.Arn" --output text 2^>nul') do (
    aws iam attach-group-policy --group-name %GROUP_NAME% --policy-arn %%a
)

echo Attaching managed policies to group...
aws iam attach-group-policy --group-name %GROUP_NAME% --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
aws iam attach-group-policy --group-name %GROUP_NAME% --policy-arn arn:aws:iam::aws:policy/AmazonSageMakerFullAccess
aws iam attach-group-policy --group-name %GROUP_NAME% --policy-arn arn:aws:iam::aws:policy/AmazonEC2FullAccess
aws iam attach-group-policy --group-name %GROUP_NAME% --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-group-policy --group-name %GROUP_NAME% --policy-arn arn:aws:iam::aws:policy/CloudWatchFullAccess
aws iam attach-group-policy --group-name %GROUP_NAME% --policy-arn arn:aws:iam::aws:policy/IAMReadOnlyAccess

echo Adding user to group...
aws iam add-user-to-group --group-name %GROUP_NAME% --user-name %USER_NAME%

echo Done! User %USER_NAME% is now in group %GROUP_NAME% with full AI access.
pause