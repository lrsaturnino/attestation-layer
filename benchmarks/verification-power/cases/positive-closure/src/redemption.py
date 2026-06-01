def finalize_redemption(wallet):
    if wallet.authorized:
        return "redemption_finalized"
    return "rejected"
