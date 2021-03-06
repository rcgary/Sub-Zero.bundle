# coding=utf-8
import datetime
import hashlib
import os
import logging
import traceback
import gzip
import types

from babelfish import Language

from json_tricks.nonp import loads#, dumps
from subzero.lib.json import dumps


from constants import mode_map
from subliminal_patch.subtitle import ModifiedSubtitle

logger = logging.getLogger(__name__)


class StoredSubtitle(object):
    """
    legacy class used for PMS LoadObject/SaveObject
    """
    score = None
    storage_type = None
    hash = None
    provider_name = None
    id = None
    date_added = None
    mode = "a"  # auto/manual/auto-better (a/m/b)
    content = None
    mods = None

    def __init__(self, score, storage_type, hash, provider_name, id, date_added=None, mode="a", content=None,
                 mods=None):
        self.score = int(score)
        self.storage_type = storage_type
        self.hash = hash
        self.provider_name = provider_name
        self.id = id
        self.date_added = date_added or datetime.datetime.now()
        self.mode = mode
        self.content = content
        self.mods = mods or []

    def add_mod(self, identifier):
        self.mods = self.mods or []
        if identifier is None:
            self.mods = []
            return

        self.mods.append(identifier)

    @property
    def mode_verbose(self):
        return mode_map.get(self.mode, "Unknown")


class JSONStoredSubtitle(object):
    score = None
    storage_type = None
    hash = None
    provider_name = None
    id = None
    date_added = None
    mode = "a"  # auto/manual/auto-better (a/m/b)
    content = None
    mods = None
    encoding = None

    def initialize(self, score, storage_type, hash, provider_name, id, date_added=None, mode="a", content=None,
                 mods=None, encoding=None):
        self.score = int(score)
        self.storage_type = storage_type
        self.hash = hash
        self.provider_name = provider_name
        self.id = id
        self.date_added = date_added or datetime.datetime.now()
        self.mode = mode
        self.content = content
        self.mods = mods or []
        self.encoding = encoding

    def add_mod(self, identifier):
        self.mods = self.mods or []
        if identifier is None:
            self.mods = []
            return

        self.mods.append(identifier)

    @property
    def mode_verbose(self):
        return mode_map.get(self.mode, "Unknown")

    def serialize(self):
        # if self.content:
        #     # content is always stored in unicode (gets converted to string with escaped unicode chars by json)
        #     try:
        #         self.content = self.content.decode(self.encoding)
        #     except UnicodeDecodeError:
        #         try:
        #             self.content = self.content.decode("utf-8")
        #         except UnicodeDecodeError:
        #             logger.error("Couldn't decode %s:%s (%s), ditching it", self.provider_name, self.id, self.encoding)
        #             return
        return self.__dict__

    def deserialize(self, data):
        if data["content"]:
            # legacy: storage was unicode; content is always present in encoded form
            if isinstance(data["content"], types.UnicodeType):
                data["content"] = data["content"].encode(data["encoding"])

        self.initialize(**data)


class StoredVideoSubtitles(object):
    """
    legacy class
    manages stored subtitles for video_id per media_part/language combination
    """
    video_id = None  # rating_key
    title = None
    parts = None
    version = None
    item_type = None  # movie / episode
    added_at = None

    def __init__(self, plex_item, version=None):
        self.video_id = str(plex_item.rating_key)

        self.title = plex_item.title
        self.parts = {}
        self.version = version
        self.item_type = plex_item.type
        self.added_at = datetime.datetime.fromtimestamp(plex_item.added_at)

    def add(self, part_id, lang, subtitle, storage_type, date_added=None, mode="a"):
        part_id = str(part_id)
        part = self.parts.get(part_id)
        if not part:
            self.parts[part_id] = {}
            part = self.parts[part_id]

        subs = part.get(lang)
        if not subs:
            part[lang] = {}
            subs = part[lang]

        sub_key = self.get_sub_key(subtitle.provider_name, subtitle.id)
        subs[sub_key] = StoredSubtitle(subtitle.score, storage_type, hashlib.md5(subtitle.content).hexdigest(),
                                       subtitle.provider_name, subtitle.id, date_added=date_added, mode=mode,
                                       content=subtitle.content, mods=subtitle.mods)
        subs["current"] = sub_key

        return True

    def get_any(self, part_id, lang):
        part_id = str(part_id)
        part = self.parts.get(part_id)
        if not part:
            return

        subs = part.get(lang)
        if not subs:
            return

        if "current" in subs and subs["current"]:
            return subs.get(subs["current"])

    def get_sub_key(self, provider_name, id):
        return provider_name, str(id)

    def __repr__(self):
        return unicode(self)

    def __unicode__(self):
        return u"%s (%s)" % (self.title, self.video_id)

    def __str__(self):
        return str(self.video_id)


class JSONStoredVideoSubtitles(object):
    """
    manages stored subtitles for video_id per media_part/language combination
    """
    video_id = None  # rating_key
    title = None
    parts = None
    version = None
    item_type = None  # movie / episode
    added_at = None

    def initialize(self, plex_item, version=None):
        self.video_id = str(plex_item.rating_key)

        self.title = plex_item.title
        self.parts = {}
        self.version = version
        self.item_type = plex_item.type
        self.added_at = datetime.datetime.fromtimestamp(plex_item.added_at)

    def deserialize(self, data):
        parts = data.pop("parts")
        self.parts = {}
        self.__dict__.update(data)

        if parts:
            for part_id, part in parts.iteritems():
                self.parts[part_id] = {}
                for language, sub_data in part.iteritems():
                    self.parts[part_id][language] = {}

                    for sub_key, subtitle_data in sub_data.iteritems():
                        if sub_key == "current":
                            if not isinstance(subtitle_data, tuple):
                                subtitle_data = tuple(subtitle_data.split("__"))
                            self.parts[part_id][language]["current"] = subtitle_data
                        else:
                            sub = JSONStoredSubtitle()

                            # legacy subtitle storage instance
                            if isinstance(subtitle_data, StoredSubtitle):
                                # subtitle_data = subtitle_data.__dict__
                                #
                                # try:
                                #     lang = Language.fromietf(language)
                                #     subtitle = ModifiedSubtitle(lang)
                                #     subtitle.content = subtitle_data["content"]
                                #     subtitle.set_encoding("utf-8")
                                #     subtitle_data["content"] = subtitle.content
                                #     subtitle_data["encoding"] = "utf-8"
                                # except:
                                #     logger.error("Legacy subtitle data could not be converted to new storage format")
                                #     continue
                                continue

                            sub.initialize(**subtitle_data)
                            if not isinstance(sub_key, tuple):
                                sub_key = tuple(sub_key.split("__"))

                            self.parts[part_id][language][sub_key] = sub

    def serialize(self):
        data = {"parts": {}}
        for key, value in self.__dict__.iteritems():
            if key != "parts":
                data[key] = value

        for part_id, part in self.parts.iteritems():
            data["parts"][part_id] = {}
            for language, sub_data in part.iteritems():
                data["parts"][part_id][language] = {}

                for sub_key, stored_subtitle in sub_data.iteritems():
                    if sub_key == "current":
                        data["parts"][part_id][language]["current"] = "__".join(stored_subtitle)
                    else:
                        if stored_subtitle.content and not stored_subtitle.encoding:
                            continue

                        serialized_sub = stored_subtitle.serialize()
                        if serialized_sub:
                            data["parts"][part_id][language]["__".join(sub_key)] = serialized_sub

        return data

    def add(self, part_id, lang, subtitle, storage_type, date_added=None, mode="a"):
        part_id = str(part_id)
        part = self.parts.get(part_id)
        if not part:
            self.parts[part_id] = {}
            part = self.parts[part_id]

        subs = part.get(lang)
        if not subs:
            part[lang] = {}
            subs = part[lang]

        sub_key = self.get_sub_key(subtitle.provider_name, subtitle.id)
        subs[sub_key] = JSONStoredSubtitle()
        subs[sub_key].initialize(subtitle.score, storage_type, hashlib.md5(subtitle.content).hexdigest(),
                                 subtitle.provider_name, subtitle.id, date_added=date_added, mode=mode,
                                 content=subtitle.content, mods=subtitle.mods, encoding="utf-8")
        subs["current"] = sub_key

        return True

    def get_any(self, part_id, lang):
        part_id = str(part_id)
        part = self.parts.get(part_id)
        if not part:
            return

        subs = part.get(str(lang))
        if not subs:
            return

        if "current" in subs and subs["current"]:
            return subs.get(subs["current"])

    def get_sub_key(self, provider_name, id):
        return provider_name, str(id)

    def __repr__(self):
        return unicode(self)

    def __unicode__(self):
        return u"%s (%s)" % (self.title, self.video_id)

    def __str__(self):
        return str(self.video_id)


class StoredSubtitlesManager(object):
    """
    manages the storage and retrieval of StoredVideoSubtitles instances for a given video_id
    """
    storage = None
    version = 3
    extension = ".json.gz"

    def __init__(self, storage, plexapi_item_getter):
        self.storage = storage
        self.get_item = plexapi_item_getter

    def destroy(self):
        self.storage = None
        self.get_item = None

    def get_storage_filename(self, video_id):
        return "subs_%s" % video_id

    @property
    def dataitems_path(self):
        return os.path.join(getattr(self.storage, "_core").storage.data_path, "DataItems")

    def get_json_data_path(self, bare_fn):
        if not bare_fn.endswith(self.extension):
            return os.path.join(self.dataitems_path, "%s%s" % (bare_fn, self.extension))
        return os.path.join(self.dataitems_path, bare_fn)

    def get_all_files(self):
        return [fn for fn in os.listdir(self.dataitems_path) if fn.startswith("subs_")]

    def get_recent_files(self, age_days=30):
        fl = []
        root = self.dataitems_path
        recent_dt = datetime.datetime.now() - datetime.timedelta(days=age_days)
        for fn in self.get_all_files():
            finfo = os.stat(os.path.join(root, fn))
            created = datetime.datetime.fromtimestamp(finfo.st_ctime)
            if created > recent_dt:
                fl.append(fn)
        return fl

    def load_recent_files(self, age_days=30):
        fl = self.get_recent_files(age_days=age_days)
        out = {}
        for fn in fl:
            data = self.load(filename=fn)
            if data:
                out[fn] = data
        return out

    def delete_missing(self, wanted_languages=set()):
        deleted = []

        def delete_fn(filename):
            if filename.endswith(".json.gz"):
                self.delete(self.get_json_data_path(filename))
            else:
                self.legacy_delete(filename)

        for fn in self.get_all_files():
            video_id = os.path.basename(fn).split(".")[0].split("subs_")[1]
            item = self.get_item(video_id)

            # item missing, delete storage
            if not item:
                delete_fn(fn)
                deleted.append(video_id)

            else:
                known_parts = []

                # wrong (legacy) info, delete storage
                if not hasattr(item, "media"):
                    delete_fn(fn)
                    deleted.append(video_id)
                    continue

                for media in item.media:
                    for part in media.parts:
                        known_parts.append(str(part.id))
                stored_subs = self.load(filename=fn)
                missing_parts = set(stored_subs.parts).difference(set(known_parts))

                changed_any = False

                # remove known info about deleted parts
                if missing_parts:
                    logger.debug("Parts removed: %s:%s, removing data", video_id, missing_parts)
                    for missing_part in missing_parts:
                        if missing_part in stored_subs.parts:
                            try:
                                del stored_subs.parts[missing_part]
                                changed_any = True
                            except:
                                pass

                # remove known info about non-existing languages
                for part_id, part in stored_subs.parts.iteritems():
                    missing_languages = set(part).difference(wanted_languages)
                    if missing_languages:
                        logger.debug("Languages removed: %s:%s:%s, removing data", video_id, part_id, missing_languages)
                        for missing_language in missing_languages:
                            try:
                                del stored_subs.parts[part_id][missing_language]
                                changed_any = True
                            except:
                                pass

                if changed_any:
                    self.save(stored_subs)

        return deleted

    def migrate_v2(self, subs_for_video):
        plex_item = self.get_item(subs_for_video.video_id)
        if not plex_item:
            return False
        subs_for_video.item_type = plex_item.type
        subs_for_video.added_at = datetime.datetime.fromtimestamp(plex_item.added_at)
        subs_for_video.version = 2
        return True

    def migrate_v3(self, subs_for_video):
        subs_for_video.version = 3
        return True

    def migrate_legacy_data(self, from_fn, to_fn):
        try:
            subs_for_video = self.storage.LoadObject(from_fn)
        except:
            logger.error("Failed to load item \"%s\": %s" % (from_fn, traceback.format_exc()))

            # delete
            return

        if not subs_for_video or not hasattr(subs_for_video, "version"):
            self.legacy_delete(from_fn)

        # migrate to our new json format
        new_subs_for_video = JSONStoredVideoSubtitles()
        new_subs_for_video.deserialize(subs_for_video.__dict__)
        subs_for_video = None
        self.save(new_subs_for_video)

        self.legacy_delete(from_fn)

        return new_subs_for_video

    def load(self, video_id=None, filename=None):
        subs_for_video = None
        bare_fn = self.get_storage_filename(video_id) if video_id else filename
        json_path = self.get_json_data_path(bare_fn)
        if os.path.exists(json_path):
            # new style data
            subs_for_video = JSONStoredVideoSubtitles()
            try:
                with gzip.open(json_path, 'rb') as f:
                    s = f.read()

                data = loads(s)
            except:
                logger.error("Couldn't load JSON data for %s", bare_fn)
                return

            subs_for_video.deserialize(data)
            data = None

        elif not bare_fn.endswith(".json.gz") and os.path.exists(os.path.join(self.dataitems_path, bare_fn)):
            subs_for_video = self.migrate_legacy_data(bare_fn, json_path)

        if not subs_for_video:
            return

        # apply possible migrations
        cur_ver = old_ver = subs_for_video.version

        if cur_ver < self.version:
            success = False
            while cur_ver < self.version:
                cur_ver += 1
                mig_func = "migrate_v%s" % cur_ver
                if hasattr(self, mig_func):
                    logger.info("Migrating subtitle storage for %s %s>%s" % (subs_for_video.video_id, old_ver, cur_ver))
                    success = getattr(self, mig_func)(subs_for_video)
                    if success is False:
                        logger.error("Couldn't migrate %s, removing data", subs_for_video.video_id)
                        self.delete(json_path)
                        break

            if cur_ver > old_ver and success:
                logger.info("Storing migrated subtitle storage for %s" % subs_for_video.video_id)
                self.save(subs_for_video)
            elif not success:
                logger.info("Migration of %s %s>%s failed" % (subs_for_video.video_id, old_ver, cur_ver))

        return subs_for_video

    def load_or_new(self, plex_item):
        subs_for_video = self.load(plex_item.rating_key)
        if not subs_for_video:
            subs_for_video = JSONStoredVideoSubtitles()
            subs_for_video.initialize(plex_item, version=self.version)
            self.save(subs_for_video)
        return subs_for_video

    def save(self, subs_for_video):
        data = subs_for_video.serialize()
        fn = self.get_json_data_path(self.get_storage_filename(subs_for_video.video_id))
        json_data = str(dumps(data, ensure_ascii=False))
        with gzip.open(fn, "wb", compresslevel=6) as f:
            f.write(json_data)

    def delete(self, filename):
        os.remove(filename)

    def legacy_save(self, subs_for_video):
        fn = self.get_storage_filename(subs_for_video.video_id)
        try:
            self.storage.SaveObject(fn, subs_for_video)
        except:
            logger.error("Failed to save item %s: %s" % (fn, traceback.format_exc()))

    def legacy_delete(self, filename):
        try:
            self.storage.Remove(filename)
        except:
            logger.error("Failed to delete item %s: %s" % (filename, traceback.format_exc()))
