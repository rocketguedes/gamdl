import re

MEDIA_TYPE_STR_MAP = {
    1: "Song",
    6: "Music Video",
}

MEDIA_RATING_STR_MAP = {
    0: "None",
    1: "Explicit",
    2: "Clean",
}

DRM_DEFAULT_KEY_MAPPING = {
    "urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed": (
        "data:text/plain;base64,AAAAOHBzc2gAAAAA7e+LqXnWSs6jyCfc1R0h7QAAABgSEAAAAAA"
        "AAAAAczEvZTEgICBI88aJmwY="
    ),
    "com.microsoft.playready": (
        "data:text/plain;charset=UTF-16;base64,vgEAAAEAAQC0ATwAVwBSAE0ASABFAEEARABF"
        "AFIAIAB4AG0AbABuAHMAPQAiAGgAdAB0AHAAOgAvAC8AcwBjAGgAZQBtAGEAcwAuAG0AaQBjAH"
        "IAbwBzAG8AZgB0AC4AYwBvAG0ALwBEAFIATQAvADIAMAAwADcALwAwADMALwBQAGwAYQB5AFIA"
        "ZQBhAGQAeQBIAGUAYQBkAGUAcgAiACAAdgBlAHIAcwBpAG8AbgA9ACIANAAuADMALgAwAC4AMA"
        "AiAD4APABEAEEAVABBAD4APABQAFIATwBUAEUAQwBUAEkATgBGAE8APgA8AEsASQBEAFMAPgA8"
        "AEsASQBEACAAQQBMAEcASQBEAD0AIgBBAEUAUwBDAEIAQwAiACAAVgBBAEwAVQBFAD0AIgBBAE"
        "EAQQBBAEEAQQBBAEEAQQBBAEIAegBNAFMAOQBsAE0AUwBBAGcASQBBAD0APQAiAD4APAAvAEsA"
        "SQBEAD4APAAvAEsASQBEAFMAPgA8AC8AUABSAE8AVABFAEMAVABJAE4ARgBPAD4APAAvAEQAQQ"
        "BUAEEAPgA8AC8AVwBSAE0ASABFAEEARABFAFIAPgA="
    ),
    "com.apple.streamingkeydelivery": "skd://itunes.apple.com/P000000000/s1/e1",
}
MP4_FORMAT_CODECS = ["ec-3", "hvc1", "audio-atmos", "audio-ec3"]
SONG_CODEC_REGEX_MAP = {
    "aac": r"audio-stereo-\d+",
    "aac-he": r"audio-HE-stereo-\d+",
    "aac-binaural": r"audio-stereo-\d+-binaural",
    "aac-downmix": r"audio-stereo-\d+-downmix",
    "aac-he-binaural": r"audio-HE-stereo-\d+-binaural",
    "aac-he-downmix": r"audio-HE-stereo-\d+-downmix",
    "atmos": r"audio-atmos-.*",
    "ac3": r"audio-ac3-.*",
    "alac": r"audio-alac-.*",
}

FOURCC_MAP = {
    "h264": "avc1",
    "h265": "hvc1",
}

UPLOADED_VIDEO_QUALITY_RANK = [
    "1080pHdVideo",
    "720pHdVideo",
    "sdVideoWithPlusAudio",
    "sdVideo",
    "sd480pVideo",
    "provisionalUploadVideo",
]

IMAGE_FILE_EXTENSION_MAP = {
    "jpeg": ".jpg",
    "tiff": ".tif",
}

VALID_URL_PATTERN = re.compile(
    r"https://(?:classical\.)?music\.apple\.com"
    r"(?:"
    r"/(?P<storefront>[a-z]{2})"
    r"/(?P<type>artist|album|playlist|song|music-video|post)"
    r"(?:/(?P<slug>[^\s/]+))?"
    r"/(?P<id>[0-9]+|pl\.[0-9a-z]{32}|pl\.u-[a-zA-Z0-9]+)"
    r"(?:\?i=(?P<sub_id>[0-9]+))?"
    r"|"
    r"(?:/(?P<library_storefront>[a-z]{2}))?"
    r"/library/(?P<library_type>playlist|albums|songs|music-videos)"
    r"/(?P<library_id>[pli]\.[a-zA-Z0-9]+)"
    r")"
)

ARTIST_AUTO_SELECT_KEY_MAP = {
    "main-albums": ("views", "full-albums"),
    "compilation-albums": ("views", "compilation-albums"),
    "live-albums": ("views", "live-albums"),
    "singles-eps": ("views", "singles"),
    "all-albums": ("relationships", "albums"),
    "top-songs": ("views", "top-songs"),
    "music-videos": ("relationships", "music-videos"),
}
ARTIST_AUTO_SELECT_STR_MAP = {
    "main-albums": "Main Albums",
    "compilation-albums": "Compilation Albums",
    "live-albums": "Live Albums",
    "singles-eps": "Singles & EPs",
    "all-albums": "All Albums",
    "top-songs": "Top Songs",
    "music-videos": "Music Videos",
}

MEDIA_CODEC_FLAVOR_MAP = {
    "aac-web": "28:ctrp256",
    "aac-he-web": "32:ctrp64",
    "aac-fps-web": "30:cbcp256",
    "aac-he-fps-web": "34:cbcp64",
}

VARIOUS_ARTISTS_TRANSLATIONS = [
    "various artists",
    "vários intérpretes",
    "vários artistas",
    "varios artistas",
    "various",
    "divers artistes",
    "verschiedene interpreten",
    "artisti vari",
    "diverse artiesten",
    "ヴァリアス・アーティスト",
    "オムニバス",
    "群星",
    "различные исполнители",
    "разные артисты",
    "여러 아티스트",
]

ROLE_TRANSLATION = {
    # Basic Translations
    "vocais": "vocals",
    "vocal": "vocals",
    "voz": "vocals",
    "vocals": "vocals",
    "composição": "composer",
    "compositor": "composer",
    "compositores": "composer",
    "letra": "lyrics",
    "lyrics": "lyrics",
    "produção": "producer",
    "produtor": "producer",
    "produtores": "producer",
    "producer": "producer",
    "programação": "programming",
    "programming": "programming",
    "dj": "dj",
    "remix": "remixer",
    "remixagem": "remixer",
    "remixador": "remixer",
    "remixer": "remixer",
    "mixagem": "mixer",
    "mixador": "mixer",
    "mixer": "mixer",
    "engenharia": "engineer",
    "engenheiro": "engineer",
    "engineer": "engineer",
    "masterização": "engineer",
    "mastering": "engineer",

    # Instruments (General)
    "baixo": "bass",
    "bass": "bass",
    "bateria": "drums",
    "drums": "drums",
    "percussão": "percussion",
    "percussion": "percussion",
    "guitarra": "guitar",
    "guitar": "guitar",
    "violão": "acoustic guitar",
    "teclado": "keyboards",
    "teclados": "keyboards",
    "keyboard": "keyboards",
    "keyboards": "keyboards",
    "piano": "piano",
    "sintetizador": "synthesizer",
    "synthesizer": "synthesizer",
    "saxofone": "saxophone",
    "saxophone": "saxophone",
    "trompete": "trumpet",
    "trumpet": "trumpet",
    "trombone": "trombone",
    "flauta": "flute",
    "flute": "flute",
    "violino": "violin",
    "violin": "violin",
    "violoncelo": "cello",
    "cello": "cello",
    "metais": "horns",
    "sopros": "horns",
    "horns": "horns",
    "cordas": "strings",
    "strings": "strings",
    "eletronicos": "electronics",
    "coral": "choir",
    "choir": "choir",
    
    # Advanced & Specific SubRoles (Portuguese to English)
    "vocais principais": "lead vocals",
    "vocal principal": "lead vocals",
    "vocal de apoio": "background vocals",
    "vocais de apoio": "background vocals",
    "coro": "background vocals",
    "guitarra eletrica": "electric guitar",
    "violao acustico": "acoustic guitar",
    "guitarra lider": "lead guitar",
    "guitarra solo": "lead guitar",
    "guitarra base": "rhythm guitar",
    "baixo de 10 cordas": "10-string bass guitar",
    "baixo eletrico": "electric bass guitar",
    "piano rhodes": "rhodes piano",
    "saxofone tenor": "tenor saxophone",
    "saxofone baritono": "baritone saxophone",
    "saxofone alto": "alto saxophone",
    "programacao de sintetizador": "synthesizer programming",
    "programacao de bateria": "drum programming",
    "bateria eletronica": "drum machine",
    "sampleador": "sampler",
    "samples (artista original)": "sampled artist",
    "todos os instrumentos": "all instruments",
    "interpretacao": "musician",
    "regencia": "conductor",
    "batida de pe": "foot stomps",
    "gritos": "screams",
    "aplausos": "hand claps",
    "palmas": "hand claps",
    "claps": "hand claps",
}

