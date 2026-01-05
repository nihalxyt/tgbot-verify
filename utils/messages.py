"""Message templates."""
from config import CHANNEL_URL, VERIFY_COST, HELP_NOTION_URL


def get_welcome_message(full_name: str, invited_by: bool = False) -> str:
    """Return the welcome message."""
    msg = (
        f"🎉 Welcome, {full_name}!\n"
        "You have successfully registered and received 1 credit.\n"
    )
    if invited_by:
        msg += "Thanks for joining via an invite link. The inviter received 2 credits.\n"

    msg += (
        "\nThis bot can automatically complete SheerID verification.\n"
        "Quick start:\n"
        "/about - Learn about the bot\n"
        "/balance - Check your credit balance\n"
        "/help - View the full command list\n\n"
        "Earn more credits:\n"
        "/qd - Daily check-in\n"
        "/invite - Invite friends\n"
        f"Join the channel: {CHANNEL_URL}"
    )
    return msg


def get_about_message() -> str:
    """Return the about message."""
    return (
        "🤖 SheerID Automated Verification Bot\n"
        "\n"
        "Features:\n"
        "- Automatically completes SheerID student/teacher verification\n"
        "- Supports Gemini One Pro, ChatGPT Teacher K12, Spotify Student, "
        "YouTube Student, and Bolt.new Teacher verifications\n"
        "\n"
        "Credits:\n"
        "- Register to receive 1 credit\n"
        "- Daily check-in: +1 credit\n"
        "- Invite friends: +2 credits per successful registration\n"
        "- Use a key (per key rules)\n"
        f"- Join the channel: {CHANNEL_URL}\n"
        "\n"
        "How to use:\n"
        "1. Start verification on the web page and copy the full verification link\n"
        "2. Send /verify, /verify2, /verify3, /verify4, or /verify5 with the link\n"
        "3. Wait for processing and review the result\n"
        "4. Bolt.new verification auto-fetches the code. For manual lookup use "
        "/getV4Code <verification_id>\n"
        "\n"
        "Send /help to see more commands."
    )


def get_help_message(is_admin: bool = False) -> str:
    """Return the help message."""
    msg = (
        "📖 SheerID Automated Verification Bot - Help\n"
        "\n"
        "User commands:\n"
        "/start - Get started (register)\n"
        "/about - Learn about the bot\n"
        "/balance - Check your credit balance\n"
        "/qd - Daily check-in (+1 credit)\n"
        "/invite - Generate an invite link (+2 credits per registration)\n"
        "/use <key> - Redeem a key for credits\n"
        f"/verify <link> - Gemini One Pro verification (-{VERIFY_COST} credits)\n"
        f"/verify2 <link> - ChatGPT Teacher K12 verification (-{VERIFY_COST} credits)\n"
        f"/verify3 <link> - Spotify Student verification (-{VERIFY_COST} credits)\n"
        f"/verify4 <link> - Bolt.new Teacher verification (-{VERIFY_COST} credits)\n"
        f"/verify5 <link> - YouTube Student Premium verification (-{VERIFY_COST} credits)\n"
        "/getV4Code <verification_id> - Fetch Bolt.new verification code\n"
        "/help - View this help message\n"
        f"Failed verifications: {HELP_NOTION_URL}\n"
    )

    if is_admin:
        msg += (
            "\nAdmin commands:\n"
            "/addbalance <user_id> <credits> - Add credits to a user\n"
            "/block <user_id> - Block a user\n"
            "/white <user_id> - Unblock a user\n"
            "/blacklist - View the blacklist\n"
            "/genkey <key> <credits> [uses] [days] - Generate a key\n"
            "/listkeys - View the key list\n"
            "/broadcast <text> - Broadcast a message to all users\n"
        )

    return msg


def get_insufficient_balance_message(current_balance: int) -> str:
    """Return the insufficient balance message."""
    return (
        f"Insufficient credits. Required: {VERIFY_COST}. Current: {current_balance}.\n\n"
        "Ways to earn credits:\n"
        "- Daily check-in: /qd\n"
        "- Invite friends: /invite\n"
        "- Redeem a key: /use <key>"
    )


def get_verify_usage_message(command: str, service_name: str) -> str:
    """Return verification command usage instructions."""
    return (
        f"Usage: {command} <SheerID link>\n\n"
        "Example:\n"
        f"{command} https://services.sheerid.com/verify/xxx/?verificationId=xxx\n\n"
        "How to get the verification link:\n"
        f"1. Visit the {service_name} verification page\n"
        "2. Start the verification flow\n"
        "3. Copy the full URL from your browser address bar\n"
        f"4. Submit it with the {command} command"
    )
