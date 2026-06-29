import asyncio
import base64
import datetime
import json
import re
from typing import AsyncGenerator, Callable
from xml.dom import minidom
from xml.etree import ElementTree

import m3u8
import structlog

from .base import AppleMusicBaseInterface
from .constants import DRM_DEFAULT_KEY_MAPPING, MP4_FORMAT_CODECS, SONG_CODEC_REGEX_MAP
from .enums import SongCodec, SyncedLyricsFormat
from .exceptions import (
    GamdlInterfaceDecryptionNotAvailableError,
    GamdlInterfaceFormatNotAvailableError,
    GamdlInterfaceMediaNotStreamableError,
)
from .types import (
    AppleMusicMedia,
    DecryptionKeyAv,
    Lyrics,
    MediaFileFormat,
    StreamInfo,
    StreamInfoAv,
)

logger = structlog.get_logger(__name__)


class AppleMusicSongInterface:
    def __init__(
        self,
        base: AppleMusicBaseInterface,
        synced_lyrics_format: SyncedLyricsFormat | list[SyncedLyricsFormat] = SyncedLyricsFormat.LRC,
        codec_priority: list[SongCodec] = [SongCodec.AAC_WEB],
        use_album_date: bool = False,
        skip_stream_info: bool = False,
        ask_codec_function: Callable[[list[dict]], dict | None] | None = None,
    ):
        self.base = base
        if isinstance(synced_lyrics_format, list):
            self.synced_lyrics_format = synced_lyrics_format
        else:
            self.synced_lyrics_format = [synced_lyrics_format]
        self.codec_priority = codec_priority
        self.use_album_date = use_album_date
        self.skip_stream_info = skip_stream_info
        self.ask_codec_function = ask_codec_function

    async def get_lyrics(
        self,
        song_metadata: dict,
    ) -> Lyrics | None:
        log = logger.bind(
            action="get_lyrics",
            song_id=song_metadata["id"],
        )

        if song_metadata["attributes"].get("playParams", {}).get("isLibrary"):
            log.debug("library_song_no_lyrics")
            return None

        if not song_metadata["attributes"].get("hasLyrics"):
            log.debug("no_lyrics")
            return None

        ttml = None
        # First, try to fetch syllable-lyrics (word-by-word synced lyrics)
        if self.base.apple_music_api:
            try:
                syllable_url = f"/v1/catalog/{self.base.apple_music_api.storefront}/songs/{song_metadata['id']}/syllable-lyrics"
                res = await self.base.apple_music_api._amp_request(syllable_url)
                if "data" in res and res["data"]:
                    ttml = res["data"][0]["attributes"].get("ttml")
                    log.debug("syllable_lyrics_fetched")
            except Exception:
                # Silently ignore and fall back to standard lyrics
                pass

        if not ttml:
            if (
                "relationships" not in song_metadata
                or "lyrics" not in song_metadata["relationships"]
            ):
                song_metadata = (
                    await self.base.apple_music_api.get_song(
                        song_metadata["id"],
                    )
                )["data"][0]

            if (
                "lyrics" in song_metadata["relationships"]
                and "data" in song_metadata["relationships"]["lyrics"]
                and len(song_metadata["relationships"]["lyrics"]["data"]) > 0
                and "attributes" in song_metadata["relationships"]["lyrics"]["data"][0]
                and song_metadata["relationships"]["lyrics"]["data"][0]["attributes"].get(
                    "ttml"
                )
                is not None
            ):
                ttml = song_metadata["relationships"]["lyrics"]["data"][0]["attributes"]["ttml"]

        if ttml:
            lyrics = self._get_lyrics(ttml)
            log.debug("success", lyrics=lyrics)
            return lyrics
        else:
            log.debug("no_lyrics_data")

    def _get_lyrics(
        self,
        lyrics_ttml: str,
    ) -> Lyrics:
        lyrics_ttml_et = ElementTree.fromstring(lyrics_ttml)
        unsynced_lyrics = []

        for div in lyrics_ttml_et.iter("{http://www.w3.org/ns/ttml}div"):
            stanza = []
            unsynced_lyrics.append(stanza)

            for p in div.iter("{http://www.w3.org/ns/ttml}p"):
                text = "".join(p.itertext()).strip()
                if text:
                    stanza.append(text)

        has_syllables = any(
            child.tag.split("}")[-1] == "span"
            for p in lyrics_ttml_et.iter("{http://www.w3.org/ns/ttml}p")
            for child in p
        )

        synced_lyrics_dict = {}
        for fmt in self.synced_lyrics_format:
            if fmt == SyncedLyricsFormat.ELRC and not has_syllables:
                continue

            synced_lyrics = []
            index = 1
            if fmt == SyncedLyricsFormat.TTML:
                synced_lyrics_dict[fmt] = minidom.parseString(lyrics_ttml).toprettyxml()
                continue

            for div in lyrics_ttml_et.iter("{http://www.w3.org/ns/ttml}div"):
                for p in div.iter("{http://www.w3.org/ns/ttml}p"):
                    if p.attrib.get("begin"):
                        if fmt == SyncedLyricsFormat.LRC:
                            synced_lyrics.append(self._get_lyrics_line_lrc(p, enhanced=False))
                        elif fmt == SyncedLyricsFormat.ELRC:
                            synced_lyrics.append(self._get_lyrics_line_lrc(p, enhanced=True))
                        elif fmt == SyncedLyricsFormat.SRT:
                            synced_lyrics.append(self._get_lyrics_line_srt(index, p))
                        index += 1
            if synced_lyrics:
                synced_lyrics_dict[fmt] = "\n".join(synced_lyrics + ["\n"])

        return Lyrics(
            synced=synced_lyrics_dict,
            unsynced=(
                "\n\n".join(["\n".join(lyric_group) for lyric_group in unsynced_lyrics])
                if unsynced_lyrics
                else None
            ),
        )

    def _parse_ttml_timestamp(
        self,
        timestamp_ttml: str,
    ) -> datetime.datetime:
        mins_secs_ms = re.findall(r"\d+", timestamp_ttml)
        ms, secs, mins = 0, 0, 0

        if len(mins_secs_ms) == 2 and ":" in timestamp_ttml:
            secs, mins = int(mins_secs_ms[-1]), int(mins_secs_ms[-2])

        elif len(mins_secs_ms) == 1:
            ms = int(mins_secs_ms[-1])

        else:
            secs = float(f"{mins_secs_ms[-2]}.{mins_secs_ms[-1]}")
            if len(mins_secs_ms) > 2:
                mins = int(mins_secs_ms[-3])

        return datetime.datetime.fromtimestamp(
            (mins * 60) + secs + (ms / 1000),
            tz=datetime.timezone.utc,
        )

    def _get_lyrics_line_srt(self, index: int, element: ElementTree.Element) -> str:
        timestamp_begin_ttml = element.attrib.get("begin")
        timestamp_end_ttml = element.attrib.get("end")
        text = "".join(element.itertext()).strip()

        timestamp_begin = self._parse_ttml_timestamp(timestamp_begin_ttml)
        timestamp_end = self._parse_ttml_timestamp(timestamp_end_ttml)

        return (
            f"{index}\n"
            f"{timestamp_begin.strftime('%H:%M:%S,%f')[:-3]} --> "
            f"{timestamp_end.strftime('%H:%M:%S,%f')[:-3]}\n"
            f"{text}\n"
        )

    def _get_lyrics_line_lrc(self, element: ElementTree.Element, enhanced: bool = False) -> str:
        timestamp_ttml = element.attrib.get("begin")
        
        # Check if we have span children for Enhanced LRC
        spans = list(element)
        if enhanced and spans and any(child.tag.split("}")[-1] == "span" for child in spans):
            line_parts = []
            for child in element:
                if child.tag.split("}")[-1] == "span":
                    span_begin = child.attrib.get("begin")
                    span_text = child.text or ""
                    span_tail = child.tail or ""
                    if span_begin:
                        ts = self._parse_ttml_timestamp(span_begin)
                        ms_new = ts.strftime("%f")[:-3]
                        if int(ms_new[-1]) >= 5:
                            ms = int(f"{int(ms_new[:2]) + 1}") * 10
                            ts += datetime.timedelta(milliseconds=ms) - datetime.timedelta(
                                microseconds=ts.microsecond
                            )
                        ts_str = f"<{ts.strftime('%M:%S.%f')[:-4]}>"
                        line_parts.append(f"{ts_str}{span_text}{span_tail}")
                    else:
                        line_parts.append(f"{span_text}{span_tail}")
            text = "".join(line_parts)
        else:
            text = "".join(element.itertext()).strip()

        timestamp = self._parse_ttml_timestamp(timestamp_ttml)
        ms_new = timestamp.strftime("%f")[:-3]

        if int(ms_new[-1]) >= 5:
            ms = int(f"{int(ms_new[:2]) + 1}") * 10
            timestamp += datetime.timedelta(milliseconds=ms) - datetime.timedelta(
                microseconds=timestamp.microsecond
            )

        return f"[{timestamp.strftime('%M:%S.%f')[:-4]}]{text}"

    def _switch_m3u8_master_url_to_default(self, m3u8_master_url: str) -> str:
        return re.sub(
            r"(P\d+)_[^/]+(\.m3u8)",
            r"\1_default\2",
            m3u8_master_url,
        )

    def _get_m3u8_from_playback(self, playback: dict) -> str | None:
        log = logger.bind(action="get_m3u8_master_url_from_playback")

        m3u8_master_url = playback["songList"][0].get("hls-playlist-url")

        if m3u8_master_url:
            m3u8_master_url = self._switch_m3u8_master_url_to_default(m3u8_master_url)
            log.debug("success", m3u8_master_url=m3u8_master_url)
            return m3u8_master_url

        log.debug("no_m3u8_master_url")

    async def _get_m3u8_master_url_from_metadata(
        self,
        song_metadata: dict,
    ) -> str | None:
        log = logger.bind(
            action="get_m3u8_master_url_from_metadata",
            song_id=song_metadata["id"],
        )

        if song_metadata["attributes"]["playParams"].get("isLibrary"):
            log.debug("library_song_no_m3u8_master_url")
            return None

        if "extendedAssetUrls" not in song_metadata["attributes"]:
            song_metadata = (
                await self.base.apple_music_api.get_song(
                    song_metadata["id"],
                )
            )["data"][0]

        enhanced = song_metadata["attributes"]["extendedAssetUrls"].get("enhancedHls")

        if enhanced:
            enhanced = self._switch_m3u8_master_url_to_default(enhanced)
            log.debug("success", m3u8_master_url=enhanced)
            return enhanced

        log.debug("no_m3u8_master_url")

        return None

    async def get_m3u8_master_url(
        self,
        playback: dict | None,
        song_metadata: dict | None,
    ) -> str | None:
        if playback:
            return self._get_m3u8_from_playback(playback)
        else:
            return await self._get_m3u8_master_url_from_metadata(song_metadata)

    async def get_stream_info(
        self,
        media_id: str,
        is_library: bool,
        m3u8_master_url: str | None = None,
        webplayback: dict | None = None,
    ) -> StreamInfoAv:
        stream_info = None

        if is_library:
            stream_info = await self._get_library_stream_info(webplayback)
        else:
            for codec in self.codec_priority:
                if codec.is_web:
                    stream_info = await self._get_web_stream_info(webplayback, codec)
                else:
                    stream_info = await self._get_stream_info(m3u8_master_url, codec)

                if stream_info:
                    break

        if not stream_info:
            raise GamdlInterfaceFormatNotAvailableError(
                media_id=media_id,
                codec=[codec.value for codec in self.codec_priority],
            )

        return stream_info

    async def _get_stream_info(
        self,
        m3u8_master_url: str | None,
        codec: SongCodec,
    ) -> StreamInfoAv | None:
        log = logger.bind(action="get_song_stream_info")

        if not m3u8_master_url:
            log.debug("no_m3u8_master_url")
            return None

        m3u8_master_obj = m3u8.loads(
            (await self.base.get_response(m3u8_master_url)).text
        )
        m3u8_master_data = m3u8_master_obj.data

        if codec == SongCodec.ASK:
            playlist = await self._get_playlist_from_user(m3u8_master_data)
        else:
            playlist = self._get_playlist_from_codec(
                m3u8_master_data,
                codec,
            )

        if playlist is None:
            log.debug("no_matching_playlist", codec=codec.value)
            return None

        stream_info = StreamInfo(use_single_content_key=False)
        stream_info.stream_url = (
            f"{m3u8_master_url.rpartition('/')[0]}/{playlist['uri']}"
        )
        stream_info.codec = playlist["stream_info"]["codecs"]
        is_mp4 = any(stream_info.codec.startswith(codec) for codec in MP4_FORMAT_CODECS)

        session_key_metadata = self._get_audio_session_key_metadata(m3u8_master_data)

        if session_key_metadata:
            asset_metadata = self._get_asset_metadata(m3u8_master_data)
            variant_id = playlist["stream_info"]["stable_variant_id"]
            drm_ids = asset_metadata[variant_id]["AUDIO-SESSION-KEY-IDS"]

            stream_info.widevine_pssh = self._get_drm_uri_from_session_key(
                session_key_metadata,
                drm_ids,
                "urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed",
            )
            stream_info.playready_pssh = self._get_drm_uri_from_session_key(
                session_key_metadata,
                drm_ids,
                "com.microsoft.playready",
            )
            stream_info.fairplay_key = self._get_drm_uri_from_session_key(
                session_key_metadata,
                drm_ids,
                "com.apple.streamingkeydelivery",
            )
        else:
            m3u8_obj = m3u8.loads(
                (await self.base.get_response(stream_info.stream_url)).text
            )

            stream_info.widevine_pssh = self._get_drm_uri_from_m3u8_keys(
                m3u8_obj,
                "urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed",
            )
            stream_info.playready_pssh = self._get_drm_uri_from_m3u8_keys(
                m3u8_obj,
                "com.microsoft.playready",
            )
            stream_info.fairplay_key = self._get_drm_uri_from_m3u8_keys(
                m3u8_obj,
                "com.apple.streamingkeydelivery",
            )

        stream_info_av = StreamInfoAv(
            audio_track=stream_info,
            file_format=MediaFileFormat.MP4 if is_mp4 else MediaFileFormat.M4A,
        )

        log.debug("success", stream_info=stream_info_av)

        return stream_info_av

    def _get_m3u8_metadata(self, m3u8_data: dict, data_id: str) -> dict | None:
        for session_data in m3u8_data.get("session_data", []):
            if session_data["data_id"] == data_id:
                return json.loads(
                    base64.b64decode(session_data["value"]).decode("utf-8")
                )
        return None

    def _get_audio_session_key_metadata(self, m3u8_data: dict) -> dict | None:
        return self._get_m3u8_metadata(
            m3u8_data,
            "com.apple.hls.AudioSessionKeyInfo",
        )

    def _get_asset_metadata(self, m3u8_data: dict) -> dict | None:
        return self._get_m3u8_metadata(
            m3u8_data,
            "com.apple.hls.audioAssetMetadata",
        )

    def _get_playlist_from_codec(
        self, m3u8_data: dict, codec: SongCodec
    ) -> dict | None:
        matching_playlists = [
            playlist
            for playlist in m3u8_data["playlists"]
            if re.fullmatch(
                SONG_CODEC_REGEX_MAP[codec.value], playlist["stream_info"]["audio"]
            )
        ]

        if not matching_playlists:
            return None

        return max(
            matching_playlists,
            key=lambda x: x["stream_info"]["average_bandwidth"],
        )

    async def _get_playlist_from_user(self, m3u8_data: dict) -> dict | None:
        if self.ask_codec_function:
            playlist = self.ask_codec_function(
                [playlist for playlist in m3u8_data["playlists"]]
            )
            if asyncio.iscoroutine(playlist):
                playlist = await playlist

            return playlist

        return None

    def _get_drm_uri_from_session_key(
        self,
        drm_infos: dict,
        drm_ids: list,
        drm_key: str,
    ) -> str | None:
        for drm_id in drm_ids:
            if drm_id != "1" and drm_key in drm_infos.get(drm_id, {}):
                return drm_infos[drm_id][drm_key]["URI"]
        return None

    def _get_drm_uri_from_m3u8_keys(
        self,
        m3u8_obj: m3u8.M3U8,
        drm_key: str,
    ) -> str | None:
        default_uri = DRM_DEFAULT_KEY_MAPPING[drm_key]

        for key in m3u8_obj.keys:
            if key.keyformat == drm_key and key.uri != default_uri:
                return key.uri
        return None

    async def _get_web_stream_info(
        self,
        webplayback: dict | None,
        codec: SongCodec,
    ) -> StreamInfoAv:
        log = logger.bind(action="get_web_song_stream_info")

        if not webplayback:
            log.debug("no_webplayback")
            return None

        flavor = codec.flavor

        stream_info = StreamInfo(
            use_cenc=codec.is_cenc,
        )
        asset = next(
            (i for i in webplayback["songList"][0]["assets"] if i["flavor"] == flavor),
            None,
        )
        if not asset:
            log.debug("no_matching_asset", codec=codec.value, flavor=flavor)
            return None

        stream_info.stream_url = asset["URL"]

        m3u8_obj = m3u8.loads(
            (await self.base.get_response(stream_info.stream_url)).text
        )

        if stream_info.use_cenc:
            stream_info.widevine_pssh = m3u8_obj.keys[0].uri
        else:
            stream_info.fairplay_key = m3u8_obj.keys[0].uri

        stream_info_av = StreamInfoAv(
            media_id=webplayback["songList"][0]["songId"],
            audio_track=stream_info,
            file_format=MediaFileFormat.M4A,
        )
        log.debug("success", stream_info=stream_info_av)

        return stream_info_av

    async def _get_library_stream_info(
        self,
        webplayback: dict | None,
    ) -> StreamInfoAv | None:
        log = logger.bind(action="get_library_song_stream_info")

        if not webplayback:
            log.debug("no_webplayback")
            return None

        stream_info = StreamInfo(drm_free=True)

        if len(webplayback["songList"][0]["assets"]) == 0:
            log.debug("no_matching_asset")
            return None
        asset = webplayback["songList"][0]["assets"][0]

        stream_info.stream_url = asset["URL"]

        stream_info_av = StreamInfoAv(
            media_id=webplayback["songList"][0]["songId"],
            audio_track=stream_info,
            file_format=MediaFileFormat.M4A,
        )
        log.debug("success", stream_info=stream_info_av)

        return stream_info_av

    async def get_media(
        self,
        media: AppleMusicMedia,
    ) -> AsyncGenerator[AppleMusicMedia, None]:
        if (
            not media.media_metadata
            or (
                not media.is_library
                and (
                    "relationships" not in media.media_metadata
                    or "artists" not in media.media_metadata["relationships"]
                    or "composers" not in media.media_metadata["relationships"]
                )
            )
        ):
            media.media_metadata = (
                await (
                    self.base.apple_music_api.get_library_song(media.media_id)
                    if media.is_library
                    else self.base.apple_music_api.get_song(media.media_id)
                )
            )["data"][0]

        if media.media_metadata["attributes"].get("playParams", {}).get("isLibrary"):
            catalog_metadata = self.base.get_catalog_metadata_from_library(
                media.media_metadata
            )
            if catalog_metadata:
                media.media_id = catalog_metadata["id"]
                media.is_library = False
                media.media_metadata = (
                    await self.base.apple_music_api.get_song(media.media_id)
                )["data"][0]

        yield media

        if not self.base.is_media_streamable(media.media_metadata):
            raise GamdlInterfaceMediaNotStreamableError(
                media_id=media.media_id,
            )

        if media.playlist_metadata:
            media.playlist_tags = self.base.get_playlist_tags(
                media.playlist_metadata,
                media.index,
            )

        media.cover = await self.base.get_cover(media.media_metadata)

        media.lyrics = await self.get_lyrics(media.media_metadata)

        if self.base.wrapper_api:
            playback = (
                await self.base.wrapper_api.get_playback(media.media_id)
                if not media.is_library
                else None
            )
            webplayback = (
                await self.base.apple_music_api.get_webplayback(
                    media.media_id,
                    media.is_library,
                )
                if media.is_library
                or any(codec.is_web for codec in self.codec_priority)
                else None
            )
        else:
            playback = None
            webplayback = await self.base.apple_music_api.get_webplayback(
                media.media_id,
                media.is_library,
            )

        relationships = media.media_metadata.get("relationships") or {}
        artists_rel = [
            a["attributes"]["name"]
            for a in (relationships.get("artists") or {}).get("data") or []
            if a.get("attributes", {}).get("name")
        ]
        
        album_artists_rel = []
        album_artist_name = None
        album_name = None
        is_single = False
        is_compilation = False
        albums_data = (relationships.get("albums") or {}).get("data") or []
        album_id = albums_data[0].get("id") if albums_data else None
        if album_id:
            try:
                album_data = await self.base.get_album_cached(album_id)
                album_artist_name = album_data["attributes"].get("artistName")
                album_name = album_data["attributes"].get("name")
                is_single = album_data["attributes"].get("isSingle", False)
                is_compilation = album_data["attributes"].get("isCompilation", False)
                album_relationships = album_data.get("relationships") or {}
                album_artists_rel = [
                    a["attributes"]["name"]
                    for a in (album_relationships.get("artists") or {}).get("data") or []
                    if a.get("attributes", {}).get("name")
                ]
            except Exception:
                pass

        artist_name = media.media_metadata["attributes"].get("artistName")
        artists = artists_rel if artists_rel else ([artist_name] if artist_name else [])
        
        various_artists_translations = [
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
        if album_artist_name and album_artist_name.strip().lower() in various_artists_translations:
            album_artists = ["Various Artists"]
        else:
            album_artists = album_artists_rel if album_artists_rel else ([album_artist_name] if album_artist_name else [])
        
        album_name_lower = album_name.lower() if album_name else ""
        if is_single or album_name_lower.endswith(" - single"):
            releasetype = "single"
        elif album_name_lower.endswith(" - ep"):
            releasetype = "ep"
        elif is_compilation:
            releasetype = "compilation"
        else:
            releasetype = "album" if album_id else None

        # Fetch composers from credits endpoint if available
        composers = []
        if not media.is_library and self.base.apple_music_api:
            try:
                credits_data = await self.base.get_song_credits_cached(media.media_id)
                for category in credits_data.get("data", []):
                    if category.get("attributes", {}).get("kind") == "composer-and-lyrics":
                        category_relationships = category.get("relationships") or {}
                        composers = [
                            artist["attributes"]["name"]
                            for artist in (category_relationships.get("credit-artists") or {}).get("data") or []
                            if artist.get("attributes", {}).get("name")
                        ]
                        break
            except Exception:
                pass

        # Fallback to standard song resource composers relationship
        if not composers:
            composers = [
                c["attributes"]["name"]
                for c in (relationships.get("composers") or {}).get("data") or []
                if c.get("attributes", {}).get("name")
            ]

        composer_sort = None
        if composers:
            if len(composers) > 1:
                composer_sort = ", ".join(composers[:-1]) + " & " + composers[-1]
            else:
                composer_sort = composers[0]

        if playback:
            media.tags = await self.base.get_tags_from_asset_info(
                playback["songList"][0]["assets"][0]["metadata"],
                media.lyrics.unsynced if media.lyrics else None,
                self.use_album_date,
                artists=artists,
                composers=composers,
                album_artists=album_artists,
                composer_sort=composer_sort,
                releasetype=releasetype,
            )
        else:
            media.tags = await self.base.get_tags_from_asset_info(
                webplayback["songList"][0]["assets"][0]["metadata"],
                media.lyrics.unsynced if media.lyrics else None,
                self.use_album_date,
                artists=artists,
                composers=composers,
                album_artists=album_artists,
                composer_sort=composer_sort,
                releasetype=releasetype,
            )

        if not self.skip_stream_info:
            m3u8_master_url = await self.get_m3u8_master_url(
                playback,
                media.media_metadata,
            )

            media.stream_info = await self.get_stream_info(
                media.media_id,
                media.is_library,
                m3u8_master_url,
                webplayback,
            )

            if media.stream_info.audio_track.drm_free:
                pass
            elif (
                not self.base.wrapper_api
                and not media.stream_info.audio_track.widevine_pssh
            ) or (
                self.base.wrapper_api
                and not media.stream_info.audio_track.fairplay_key
                and not media.stream_info.audio_track.use_cenc
            ):
                raise GamdlInterfaceDecryptionNotAvailableError(media_id=media.media_id)
            elif media.stream_info.audio_track.widevine_pssh:
                media.decryption_key = DecryptionKeyAv(
                    audio_track=await self.base.get_decryption_key(
                        media.stream_info.audio_track.widevine_pssh,
                        media.media_id,
                    )
                )

        media.partial = False

        yield media
