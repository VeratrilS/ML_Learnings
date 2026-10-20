import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "apply_assist"))
import linkedin_apply  # noqa: E402


def test_job_id_from_link_shapes():
    assert linkedin_apply.job_id("https://www.linkedin.com/jobs/view/4478259021/") == "4478259021"
    assert linkedin_apply.job_id(
        "https://in.linkedin.com/jobs/view/software-engineer-at-sentraforge-ai-4478259021") == "4478259021"
    assert linkedin_apply.job_id("https://www.linkedin.com/jobs/collections/?currentJobId=4012345678") == "4012345678"
    assert linkedin_apply.job_id("https://www.linkedin.com/in/someone") is None


def test_sent_message_detected():
    assert linkedin_apply.SENT.search("Your application was sent to SentraForge ai")
    assert linkedin_apply.SENT.search("Applied 2 minutes ago")
    assert not linkedin_apply.SENT.search("Easy Apply")
