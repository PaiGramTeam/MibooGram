from simnet.models.zzz.wish import ZZZBannerType

ZZZGF_VERSION = "v1.0"


GACHA_TYPE_LIST = {
    ZZZBannerType.STANDARD: "常驻调频",
    ZZZBannerType.CHARACTER: "代理人调频",
    ZZZBannerType.WEAPON: "音擎调频",
    ZZZBannerType.BANGBOO: "邦布调频",
}
GACHA_TYPE_LIST_REVERSE = {v: k for k, v in GACHA_TYPE_LIST.items()}
