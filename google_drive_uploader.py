import os
import io
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

class GoogleDriveUploader:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/drive.file']
        self.creds = None
        self.service = None
        self.setup_credentials()

    def setup_credentials(self):
        """Setup Google Drive API credentials using Service Account"""
        try:
            # Use Service Account credentials from environment variable
            credentials_json = os.getenv('GOOGLE_DRIVE_CREDENTIALS_JSON')
            if credentials_json:
                try:
                    credentials_info = json.loads(credentials_json)

                    # Check if it's a Service Account credential
                    if credentials_info.get('type') == 'service_account':
                        self.creds = service_account.Credentials.from_service_account_info(
                            credentials_info, 
                            scopes=self.SCOPES
                        )

                        self.service = build('drive', 'v3', credentials=self.creds)
                        print("✅ Google Drive API initialized with Service Account")
                        return True
                    else:
                        print("❌ Credentials must be Service Account type")
                        return False

                except json.JSONDecodeError:
                    print("❌ Invalid JSON format in GOOGLE_DRIVE_CREDENTIALS_JSON")
                    return False
                except Exception as cred_error:
                    print(f"❌ Google Drive credential setup error: {cred_error}")
                    return False
            else:
                print("❌ Google Drive credentials not found in environment")
                print("📝 Please set GOOGLE_DRIVE_CREDENTIALS_JSON in Secrets")
                return False

        except Exception as e:
            print(f"❌ Google Drive setup error: {e}")
            return False

    def upload_file(self, file_path, file_name=None):
        """Upload file to Google Drive and return shareable link"""
        if not self.service:
            print("❌ Google Drive service not initialized")
            return None

        try:
            if not file_name:
                file_name = os.path.basename(file_path)

            # File metadata
            file_metadata = {
                'name': file_name,
                'parents': [os.getenv('GOOGLE_DRIVE_FOLDER_ID', 'root')]  # Use folder ID from env or root
            }

            # Upload file
            with open(file_path, 'rb') as file_data:
                media = MediaIoBaseUpload(
                    io.BytesIO(file_data.read()),
                    mimetype='application/pdf',
                    resumable=True
                )

                file_obj = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

            file_id = file_obj.get('id')

            # Make file shareable
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }

            self.service.permissions().create(
                fileId=file_id,
                body=permission
            ).execute()

            # Get shareable link
            shareable_link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
            download_link = f"https://drive.google.com/uc?id={file_id}&export=download"

            print(f"✅ File uploaded to Google Drive: {file_name}")
            return {
                'file_id': file_id,
                'shareable_link': shareable_link,
                'download_link': download_link,
                'file_name': file_name
            }

        except Exception as e:
            print(f"❌ Google Drive upload error: {e}")
            return None

    def delete_file(self, file_id):
        """Delete file from Google Drive"""
        try:
            if self.service:
                self.service.files().delete(fileId=file_id).execute()
                print(f"🗑️ Deleted file from Google Drive: {file_id}")
                return True
        except Exception as e:
            print(f"❌ Google Drive delete error: {e}")
            return False