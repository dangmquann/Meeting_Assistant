import os
from minio import Minio
from minio.error import S3Error
from controller.utils import load_cfg
import datetime

CFG_FILE = "./controller/config.yaml"

cfg = load_cfg(CFG_FILE)
datalake_cfg = cfg["datalake"]

class MinioClient:
    def __init__(self):
        """
        Initialize Minio client using datalake config.
        """
        self.endpoint = datalake_cfg["endpoint"]
        self.access_key = datalake_cfg["access_key"]
        self.secret_key = datalake_cfg["secret_key"]
        self.bucket_name = datalake_cfg["bucket_name"]
        self.folder_name = datalake_cfg.get("folder_name", "")
        self.client = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=False
        )

    def make_bucket(self):
        """
        Create a bucket if it does not exist (using config).
        """
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                print(f"Bucket '{self.bucket_name}' created.")
            else:
                print(f"Bucket '{self.bucket_name}' already exists.")
        except S3Error as e:
            print(f"Error creating bucket '{self.bucket_name}': {e}")

    def upload_file(self, file_path, object_name=None):
        """
        Upload a file to the bucket/folder from config.
        :param file_path: Local path of the file to upload
        :param object_name: Object name in the bucket (optional)
        """
        if object_name is None:
            object_name = os.path.basename(file_path)
        if self.folder_name:
            object_name = f"{self.folder_name}/{object_name}"
        try:
            self.client.fput_object(self.bucket_name, object_name, file_path)
            print(f"File '{file_path}' uploaded to '{self.bucket_name}/{object_name}'.")
            return self.get_object_url(object_name)
        except S3Error as e:
            print(f"Error uploading file '{file_path}': {e}")
            return None


    def get_object_url(self, object_name, expiry=3600):
        """
        Get a presigned URL for the object in config bucket/folder.
        :param object_name: Object name (relative to folder if set)
        :param expiry: URL expiry time in seconds (default: 1 hour)
        :return: Presigned URL as string
        """
        if self.folder_name and not object_name.startswith(self.folder_name):
            object_name = f"{self.folder_name}/{object_name}"
        try:
            expires = datetime.timedelta(seconds=expiry)
            url = self.client.presigned_get_object(self.bucket_name, object_name, expires=expires)
            return url
        except S3Error as e:
            print(f"Error generating URL: {e}")
            return None
        
if __name__ == "__main__":
    minio_client = MinioClient()
    minio_client.make_bucket()
    test_file = "test.txt"
    with open (test_file, "w") as f:
        f.write("This is a test file for MinIO upload.\n")
    
    minio_client.upload_file(test_file, object_name="test.txt")
    url = minio_client.get_object_url("test.txt")
    if url:
        print(f"File uploaded successfully. Access it at: {url}")   
