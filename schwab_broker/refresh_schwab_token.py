from SchwabAuthManager import SchwabAuthManager, SchwabAuthError


def main() -> None:
    auth = SchwabAuthManager(env_file="schwab.env", token_file="schwab_token.env")
    print("Open this URL in a browser and complete Schwab login:\n")
    print(auth.build_authorize_url())
    print("\nPaste the full callback URL after approval:\n")
    callback_url = input().strip()
    try:
        auth.exchange_callback_url_for_tokens(callback_url)
        print("schwab_token.env updated successfully")
    except SchwabAuthError as e:
        print(f"Token refresh/auth failed: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

