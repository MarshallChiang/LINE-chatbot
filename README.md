## LINE-chatbot
function integrated with rekognition and use line-bot-sdk as client input.
<img src=https://static-github.s3-ap-northeast-1.amazonaws.com/Chatbot_image_1.png>

## Environment Setup

```bash
$ cd path/to/project
$ pip install -r requirements.txt -t .
```
After implement to AWS lambda and integrated with API Gateway, setup os environment of server endpoint and configuration source.

```bash
$ aws lambda update-function-configuration --function-name LINE-Chatbot \
    --environment "Variables={
    Bucket=bucket_name, \
    CollectionId=collection_id, \
    aws_access_key_id=aws_key,
    aws_secret_access_aws_secret, \
    channel_access_token=line_token, \
    channel_secret=line_secret, \
    region_name=region}"
```

## Demonstration

<img src=https://static-github.s3-ap-northeast-1.amazonaws.com/Chatbot_image_2.gif width=30% height=30%>
    
