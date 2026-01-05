"""SheerID teacher verification main program (Bolt.now)."""
import re
import random
import logging
import httpx
from typing import Dict, Optional, Tuple

from . import config
from .name_generator import NameGenerator, generate_birth_date
from .img_generator import generate_images, generate_psu_email

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)


class SheerIDVerifier:
    """SheerID teacher verifier."""

    def __init__(self, install_page_url: str, verification_id: Optional[str] = None):
        self.install_page_url = self.normalize_url(install_page_url)
        self.verification_id = verification_id
        self.external_user_id = self.parse_external_user_id(self.install_page_url)
        self.device_fingerprint = self._generate_device_fingerprint()
        self.http_client = httpx.Client(timeout=30.0)

    def __del__(self):
        if hasattr(self, "http_client"):
            self.http_client.close()

    @staticmethod
    def _generate_device_fingerprint() -> str:
        chars = "0123456789abcdef"
        return "".join(random.choice(chars) for _ in range(32))

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize the URL (kept as-is for compatibility)."""
        return url

    @staticmethod
    def parse_verification_id(url: str) -> Optional[str]:
        match = re.search(r"verificationId=([a-f0-9]+)", url, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def parse_external_user_id(url: str) -> Optional[str]:
        match = re.search(r"externalUserId=([^&]+)", url, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def create_verification(self) -> str:
        """Request a new verification ID via installPageUrl."""
        body = {
            "programId": config.PROGRAM_ID,
            "installPageUrl": self.install_page_url,
        }
        data, status = self._sheerid_request(
            "POST", f"{config.MY_SHEERID_URL}/rest/v2/verification/", body
        )
        if status != 200 or not isinstance(data, dict) or not data.get("verificationId"):
            raise Exception(f"Failed to create verification (status {status}): {data}")

        self.verification_id = data["verificationId"]
        logger.info("✅ Retrieved verificationId: %s", self.verification_id)
        return self.verification_id

    def _sheerid_request(
        self, method: str, url: str, body: Optional[Dict] = None
    ) -> Tuple[Dict, int]:
        """Send a SheerID API request."""
        headers = {
            "Content-Type": "application/json",
        }

        response = self.http_client.request(
            method=method, url=url, json=body, headers=headers
        )
        try:
            data = response.json()
        except Exception:
            data = response.text
        return data, response.status_code

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
        """Run the teacher verification flow."""
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
            if not self.external_user_id:
                self.external_user_id = str(random.randint(1000000, 9999999))

            if not self.verification_id:
                logger.info("Requesting a new verificationId...")
                self.create_verification()

            logger.info("Teacher: %s %s", first_name, last_name)
            logger.info("Email: %s", email)
            logger.info("School: %s", school["name"])
            logger.info("Birth date: %s", birth_date)
            logger.info("Verification ID: %s", self.verification_id)

            # Generate teacher PNGs.
            logger.info("Step 1/5: Generating teacher PNG documents...")
            assets = generate_images(first_name, last_name, school_id)
            for asset in assets:
                logger.info(
                    "  - %s size: %.2fKB",
                    asset["file_name"],
                    len(asset["data"]) / 1024,
                )

            # Submit teacher information.
            logger.info("Step 2/5: Submitting teacher information...")
            step2_body = {
                "firstName": first_name,
                "lastName": last_name,
                "birthDate": "",
                "email": email,
                "phoneNumber": "",
                "organization": {
                    "id": int(school_id),
                    "idExtended": school["idExtended"],
                    "name": school["name"],
                },
                "deviceFingerprintHash": self.device_fingerprint,
                "externalUserId": self.external_user_id,
                "locale": "en-US",
                "metadata": {
                    "marketConsentValue": True,
                    "refererUrl": self.install_page_url,
                    "externalUserId": self.external_user_id,
                    "flags": '{"doc-upload-considerations":"default","doc-upload-may24":"default","doc-upload-redesign-use-legacy-message-keys":false,"docUpload-assertion-checklist":"default","include-cvec-field-france-student":"not-labeled-optional","org-search-overlay":"default","org-selected-display":"default"}',
                    "submissionOptIn": "By submitting the personal information above, I acknowledge that my personal information is being collected under the privacy policy of the business from which I am seeking a discount",
                },
            }

            step2_data, step2_status = self._sheerid_request(
                "POST",
                f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/collectTeacherPersonalInfo",
                step2_body,
            )

            if step2_status != 200:
                raise Exception(f"Step 2 failed (status {step2_status}): {step2_data}")
            if isinstance(step2_data, dict) and step2_data.get("currentStep") == "error":
                error_msg = ", ".join(step2_data.get("errorIds", ["Unknown error"]))
                raise Exception(f"Step 2 error: {error_msg}")

            logger.info(
                "✅ Step 2 completed: %s",
                getattr(step2_data, "get", lambda k, d=None: d)("currentStep"),
            )
            current_step = (
                step2_data.get("currentStep", current_step) if isinstance(step2_data, dict) else current_step
            )

            # Skip SSO if required.
            if current_step in ["sso", "collectTeacherPersonalInfo"]:
                logger.info("Step 3/5: Skipping SSO verification...")
                step3_data, _ = self._sheerid_request(
                    "DELETE",
                    f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/sso",
                )
                logger.info(
                    "✅ Step 3 completed: %s",
                    getattr(step3_data, "get", lambda k, d=None: d)("currentStep"),
                )
                current_step = (
                    step3_data.get("currentStep", current_step) if isinstance(step3_data, dict) else current_step
                )

            # Request upload URLs and upload documents.
            logger.info("Step 4/5: Requesting upload URLs...")
            step4_body = {
                "files": [
                    {
                        "fileName": asset["file_name"],
                        "mimeType": "image/png",
                        "fileSize": len(asset["data"]),
                    }
                    for asset in assets
                ]
            }
            step4_data, step4_status = self._sheerid_request(
                "POST",
                f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/docUpload",
                step4_body,
            )
            if step4_status != 200 or not isinstance(step4_data, dict) or not step4_data.get("documents"):
                raise Exception(f"Failed to retrieve upload URLs: {step4_data}")

            documents = step4_data["documents"]
            if len(documents) != len(assets):
                raise Exception("Upload task count does not match file count")

            for doc, asset in zip(documents, assets):
                upload_url = doc.get("uploadUrl")
                if not upload_url:
                    raise Exception("Missing upload URL")
                if not self._upload_to_s3(upload_url, asset["data"]):
                    raise Exception(f"S3 upload failed: {asset['file_name']}")
                logger.info("✅ Uploaded %s", asset["file_name"])

            step6_data, _ = self._sheerid_request(
                "POST",
                f"{config.SHEERID_BASE_URL}/rest/v2/verification/{self.verification_id}/step/completeDocUpload",
            )
            logger.info(
                "✅ Document submission completed: %s",
                getattr(step6_data, "get", lambda k, d=None: d)("currentStep"),
            )

            # 获取最终状态（包含 rewardCode）
            final_status, _ = self._sheerid_request(
                "GET",
                f"{config.MY_SHEERID_URL}/rest/v2/verification/{self.verification_id}",
            )
            reward_code = None
            if isinstance(final_status, dict):
                reward_code = final_status.get("rewardCode") or final_status.get("rewardData", {}).get("rewardCode")

            return {
                "success": True,
                "pending": final_status.get("currentStep") != "success" if isinstance(final_status, dict) else True,
                "message": "Documents submitted and pending review."
                if not isinstance(final_status, dict) or final_status.get("currentStep") != "success"
                else "Verification successful.",
                "verification_id": self.verification_id,
                "redirect_url": final_status.get("redirectUrl") if isinstance(final_status, dict) else None,
                "reward_code": reward_code,
                "status": final_status,
            }

        except Exception as e:
            logger.error("❌ Verification failed: %s", e)
            return {"success": False, "message": str(e), "verification_id": self.verification_id}


def main():
    """Main entry point for CLI usage."""
    import sys

    print("=" * 60)
    print("SheerID Teacher Verification Tool (Python)")
    print("=" * 60)
    print()

    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Enter the SheerID verification URL (including externalUserId): ").strip()

    if not url:
        print("❌ Error: No URL provided")
        sys.exit(1)

    verification_id = SheerIDVerifier.parse_verification_id(url)
    verifier = SheerIDVerifier(url, verification_id=verification_id)

    print(f"👉 Using link: {verifier.install_page_url}")
    if verifier.verification_id:
        print(f"Parsed verificationId: {verifier.verification_id}")
    if verifier.external_user_id:
        print(f"externalUserId: {verifier.external_user_id}")
    print()

    result = verifier.verify()

    print()
    print("=" * 60)
    print("Verification Result:")
    print("=" * 60)
    print(f"Status: {'✅ Success' if result['success'] else '❌ Failed'}")
    print(f"Message: {result['message']}")
    if result.get("reward_code"):
        print(f"Reward code: {result['reward_code']}")
    if result.get("redirect_url"):
        print(f"Redirect URL: {result['redirect_url']}")
    print("=" * 60)

    return 0 if result["success"] else 1


if __name__ == "__main__":
    exit(main())
