import boto3
from datetime import datetime, timezone


def get_s3_bucket_details(access_key, secret_key, session_token, bucket_name, start_date, end_date):
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)

        boto3_s3 = boto3.client(
            's3',
            'us-east-1',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token
        )

        paginator = boto3_s3.get_paginator('list_objects_v2')

        files = []
        for page in paginator.paginate(Bucket=bucket_name):
            for key_obj in page.get('Contents', []):
                last_modified = key_obj['LastModified']

                if start_dt <= last_modified < end_dt:
                    file_name = key_obj['Key']
                    files.append({
                        'file_name': file_name,
                        'last_modified': last_modified.replace(tzinfo=None).isoformat()
                    })

        return {
            'bucket_name': bucket_name,
            'start_date': start_date,
            'end_date': end_date,
            'file_count': len(files),
            'files': files
        }
    except Exception as e:
        return {'error': str(e)}
