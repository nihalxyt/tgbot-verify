"""SheerID student verification main program."""
import re
import random
import logging
import httpx
from typing import Dict, Optional, Tuple

from . import config
from .name_generator import NameGenerator, generate_email, generate_birth_date
from .img_generator import generate_psu_email, generate_image

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class SheerIDVerifier:
    """SheerID student verifier."""

    def __init__(self, verification_id: str):
        self.verification_id = verification_id
        self.device_fingerprint = self._generate_device_fingerprint()
        self.http_client = httpx.Client(timeout=30.0)

    def __del__(self):
        if hasattr(self, "http_client"):
            self.http_client.close()

    @staticmethod
    def _generate_device_fingerprint() -> str:
        chars = '0123456789abcdef'
        return ''.join(random.choice(chars) for _ in range(32))

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize the URL (kept as-is)."""
        return url

    @staticmethod
    def parse_verification_id(url: str) -> Optional[str]:
        match = re.search(r"verificationId=([a-f0-9]+)", url, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _sheerid_request(
        self, method: str, url: str, body: Optional[Dict] = None
    ) -> Tuple[Dict, int]:
        """Send a SheerID API request."""
        headers = {
            "Content-Type": "application/json",
        }

        try:
            response = self.http_client.request(
                method=method, url=url, json=body, headers=headers
            )
            try:
                data = response.json()
            except Exception:
                data = response.text
            return data, response.status_code
        except Exception as e:
            logger.error("SheerID request failed: %s", e)
            raise

    def _upload_to_s3(self, upload_url: str, img_data: bytes) -> bool:
        """Upload PNG to S3."""
        try:
            headers = {"Content-Type": "image/png"}
            response = self.http_client.put(
                upload_url, content=img_data, headers=headers, timeout=60.0
            )
            return 200 <= response.status_code < 300
        except Exception as e:
            logger.error("S3 upload failed: %s", e)
            return False

    def verify(
        self,
        first_name: str = None,
        last_name: str = None,
        email: str = None,
        birth_date: str = None,
        school_id: str = None,
    ) -> Dict:
        """Run the verification flow without status polling to reduce latency."""
        try:
            current_step = "initial"

            if not first_name or not last_name:
                name = NameGenerator.generate()
                first_name = name["first_name"]
                last_name = name["last_name"]

            school_id = school_id or config.DEFAULT_SCHOOL_ID
            school = config.SCHOOLS[school_id]

            if not email:
                email = generate_psu_email(first_name, last_name)
            if not birth_date:
                birth_date = generate_birth_date()

            logger.info("Student: %s %s", first_name, last_name)
            logger.info("Email: %s", email)
            logger.info("School: %s", school["name"])
            logger.info("Birth date: %s", birth_date)
            logger.info("Verification ID: %s", self.verification_id)

            # 生成学生证 PNG
            logger.info("Step 1/4: Generating student ID PNG...")
            img_data = generate_image(first_name, last_name, school_id)
            file_size = len(img_data)
            logger.info("✅ PNG size: %.2fKB", file_size / 1024)

            # 提交学生信息
            logger.info("Step 2/4: Submitting student information...")
            step2_body = {
                "firstName": first_name,
                "lastName": last_name,
                "birthDate": birth_date,
                "email": email,
                "phoneNumber": "",
                "organization": {
                    "id": int(school_id),
                    "idExtended": school["idExtended"],
                    "name": school["name"],
                },
                "deviceFingerprintHash": self.device_fingerprint,
                "locale": "en-US",
                "metadata": {
                    "marketConsentValue": False,
                    "refererUrl": f"{config.SHEERID_BASE_URL}/verify/{config.PROGRAM_ID}/?verificationId={self.verification_id}",
                    "verificationId": self.verification_id,
                    "flags": '{"collect-info-step-email-first":"default","doc-upload-considerations":"default","doc-upload-may24":"default","doc-upload-redesign-use-legacy-message-keys":false,"docUpload-assertion-checklist":"default","font-size":"default","include-cvec-field-france-student":"not-labeled-optional"}',
                    "submissionOptIn": "By submitting the personal information above, I acknowledge that my personal information is being collected under the privacy policy of the business from which I am seeking a discount",
                },
            }

            step2_data, step2_status = self._sheerid_request(
                "POST",
                f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/collectStudentPersonalInfo",
                step2_body,
            )

            if step2_status != 200:
                raise Exception(f"Step 2 failed (status {step2_status}): {step2_data}")
            if step2_data.get("currentStep") == "error":
                error_msg = ", ".join(step2_data.get("errorIds", ["Unknown error"]))
                raise Exception(f"Step 2 error: {error_msg}")

            logger.info("✅ Step 2 completed: %s", step2_data.get("currentStep"))
            current_step = step2_data.get("currentStep", current_step)

            # Skip SSO if required.
            if current_step in ["sso", "collectStudentPersonalInfo"]:
                logger.info("Step 3/4: Skipping SSO verification...")
                step3_data, _ = self._sheerid_request(
                    "DELETE",
                    f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/sso",
                )
                logger.info("✅ Step 3 completed: %s", step3_data.get("currentStep"))
                current_step = step3_data.get("currentStep", current_step)

            # 上传文档并完成提交
            logger.info("Step 4/4: Requesting and uploading documents...")
            step4_body = {
                "files": [
                    {"fileName": "student_card.png", "mimeType": "image/png", "fileSize": file_size}
                ]
            }
            step4_data, step4_status = self._sheerid_request(
                "POST",
                f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/docUpload",
                step4_body,
            )
            if not step4_data.get("documents"):
                raise Exception("Failed to retrieve upload URL")

            upload_url = step4_data["documents"][0]["uploadUrl"]
            logger.info("✅ Upload URL retrieved")
            if not self._upload_to_s3(upload_url, img_data):
                raise Exception("S3 upload failed")
            logger.info("✅ Student ID uploaded successfully")

            step6_data, _ = self._sheerid_request(
                "POST",
                f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/completeDocUpload",
            )
            logger.info("✅ Document submission completed: %s", step6_data.get("currentStep"))
            final_status = step6_data

            # 不做状态轮询，直接返回等待审核
            return {
                "success": True,
                "pending": True,
                "message": "Documents submitted and pending review.",
                "verification_id": self.verification_id,
                "redirect_url": final_status.get("redirectUrl"),
                "status": final_status,
            }

        except Exception as e:
            logger.error("❌ Verification failed: %s", e)
            return {"success": False, "message": str(e), "verification_id": self.verification_id}


def main():
    """Main entry point for CLI usage."""
    import sys

    print("=" * 60)
    print("SheerID Student Verification Tool (Python)")
    print("=" * 60)
    print()

    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Enter the SheerID verification URL: ").strip()

    if not url:
        print("❌ Error: No URL provided")
        sys.exit(1)

    verification_id = SheerIDVerifier.parse_verification_id(url)
    if not verification_id:
        print("❌ Error: Invalid verification ID format")
        sys.exit(1)

    print(f"✅ Parsed verification ID: {verification_id}")
    print()

    verifier = SheerIDVerifier(verification_id)
    result = verifier.verify()

    print()
    print("=" * 60)
    print("Verification Result:")
    print("=" * 60)
    print(f"Status: {'✅ Success' if result['success'] else '❌ Failed'}")
    print(f"Message: {result['message']}")
    if result.get("redirect_url"):
        print(f"Redirect URL: {result['redirect_url']}")
    print("=" * 60)

    return 0 if result["success"] else 1


if __name__ == "__main__":
    exit(main())
