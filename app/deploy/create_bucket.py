"""写真・音声の一時保存用 S3 バケットを作る（EC2の中で1回だけ実行）。

- AWSの鍵は使わない。EC2に付けた LabInstanceProfile の一時的な認証情報で動く
- 公開はすべてブロック、保存時は暗号化
- uploads/ の下のファイルは 1日で自動削除（アプリが消し忘れても残らない）

使い方: python create_bucket.py <リージョン>   → 作ったバケット名を表示する
"""
import secrets
import sys

import boto3
from botocore.exceptions import ClientError

region = sys.argv[1] if len(sys.argv) > 1 else "us-east-1"
s3 = boto3.client("s3", region_name=region)
account = boto3.client("sts", region_name=region).get_caller_identity()["Account"]
name = f"skima-uploads-{account}-{secrets.token_hex(3)}"

try:
    if region == "us-east-1":
        s3.create_bucket(Bucket=name)
    else:
        s3.create_bucket(Bucket=name, CreateBucketConfiguration={"LocationConstraint": region})
except ClientError as e:
    sys.exit(f"バケットを作れませんでした: {e}")

s3.put_public_access_block(
    Bucket=name,
    PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True,
        "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
    },
)
s3.put_bucket_encryption(
    Bucket=name,
    ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
)
s3.put_bucket_lifecycle_configuration(
    Bucket=name,
    LifecycleConfiguration={"Rules": [{
        "ID": "delete-uploads-after-1-day",
        "Filter": {"Prefix": "uploads/"},
        "Status": "Enabled",
        "Expiration": {"Days": 1},
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
    }]},
)
print(name)
