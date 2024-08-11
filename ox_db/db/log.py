"""
log handles the database work flow
"""

import os
import bson
import json
from datetime import datetime
from typing import Dict, TypeAlias, Union, List, Optional, Any
from ox_db.db.types import embd, uids

from ox_doc.ld import OxDoc
from ox_db.ai.vector import Model

from ox_db.utils.dp import gen_uid, strorlist_to_list


class Oxdb:
    def __init__(self, db: str = "", db_path: Optional[str] = None):
        """
        Initialize instances of the Log class

        Args:
            db (str, optional): The name of the database. Defaults to "".
            db_path (Optional[str], optional): The path to the database directory. Defaults to None.
        """
        self.set_db(db, db_path)
        self.vec = Model()

    def set_db(self, db: str, db_path: Optional[str] = None) -> str:
        """
        Sets the database path.

        Args:
            db (str): The database name.
            db_path (Optional[str]): The database path.

        Returns:
            str: The path to the database.
        """
        self.db = db
        self.db_path = (
            db_path
            if db_path
            else os.path.join(os.path.expanduser("~"), "ox-db", db + ".oxdb")
        )
        os.makedirs(self.db_path, exist_ok=True)
        return self.db_path

    def get_db(self) -> str:
        """
        Returns the current database path.

        Returns:
            str: The database path.
        """
        return self.db

    def get_doc(self, doc: Optional[str] = None):
        """
        get the document instances

        Args:
            doc (Optional[str], optional): The document name. Defaults to None.

        Returns:
             The doc instances.
        """
        self.doc = Doc(doc)
        self.doc.connect_db(self.db_path, self.vec)
        return self.doc

    def get_docs(self) -> list:
        """
        Returns the current document.

        Returns:
            list: of all docs
        """
        pass

    def info(self) -> dict:

        res = {
            "db": self.db,
            "db_path": self.db_path,
            "doc_name": self.doc.doc_name,
            "doc_path": self.doc.doc_path,
            "vec_model": self.vec.md_name,
        }
        return res


class Doc:
    def __init__(self, doc: Optional[str] = None):
        """db doc handler"""
        self.doc_name = doc or "log-" + datetime.now().strftime("[%d_%m_%Y]")

    # def __del__(self):
    #     print("db destroyed : presisting")
    #     self.save_index()

    # def __exit__(self, exc_type, exc_value, traceback):
    #     print("Exiting the db : presisting")
    #     self.save_index()

    def connect_db(self, db_path, vec):
        self.db_path = db_path
        self.vec = vec
        self.doc_path = os.path.join(self.db_path, self.doc_name)
        os.makedirs(self.doc_path, exist_ok=True)
        self.doc_index_path = os.path.join(self.doc_path, self.doc_name + ".index")

        self.load_index()
        self.data_oxd = self._create_oxd("data.oxd")
        self.vec_oxd = self._create_oxd("vec.oxd")
        self.doc_reg["vec_model"] = self.vec.md_name
        self.save_index()

    def _create_oxd(self, oxd_doc_name):
        oxd_doc_path = os.path.join(self.doc_path, oxd_doc_name)
        return OxDoc(oxd_doc_path)

    def get_doc_name(self) -> str:
        """
        Returns the current document.

        Returns:
            str: The document name.
        """
        return self.doc_name

    def info(self) -> dict:
        res = {
            "doc_name": self.doc_name,
            "doc_path": self.doc_path,
            "doc_reg": self.doc_reg,
        }
        return res

    def push(
        self,
        data: Any,
        embeddings: embd = True,
        description: Optional[any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        key: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Pushes data to the log file. Can be called with either data or both key and data.

        Args:
            data (Any): The data to be logged.
            embeddings (bool, optional): Whether to generate embeddings. Defaults to True.
            description (Optional[any], optional): Description related to the data. Defaults to None.
            metadata (Optional[dict], optional): metadata related to the data. Defaults to None.
            key (Optional[str], optional): The key for the log entry. Defaults to None.
            data_type (Optional[str], optional): The data_type of log entry. Defaults to None.

        Returns:
            str: The unique ID of the log entry.
        """
        doc = self.get_doc_name()
        uid = gen_uid()

        if data == "" or data is None:
            raise ValueError("ox-db : No data provided for logging")
        doc_unit = {"data": data, "description": description}

        index_unit = {
            "uid": uid,
            "key": key or "key",
            "doc": doc,
            "time": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%d-%m-%Y"),
            "metadata": metadata,
            "data_type": kwargs.get("data_type", type(data).__name__),
        }

        self.push_index(uid, index_unit, doc + ".index")
        self.data_oxd.set(uid, doc_unit)
        if embeddings:
            encoded_embeddings = (
                encoded_embeddings if embeddings != True else self.vec.encode(data)
            )
            self.vec_oxd.set(uid, encoded_embeddings)

        return uid

    def pull(
        self,
        uid: uids = None,
        key: Optional[str] = None,
        time: Optional[str] = None,
        date: Optional[str] = None,
        docfile: Optional[str] = "data.oxd",
        where: Optional[dict] = None,
        where_data: Optional[dict] = None,
    ) -> List[dict]:
        """
        Retrieves log entries based on unique ID, key, time, or date.

        Args:
            uid (uids): The unique ID of the log entry. Defaults to None.
            key (Optional[str], optional): The key of the log entry. Defaults to None.
            time (Optional[str], optional): The time of the log entry. Defaults to None.
            date (Optional[str], optional): The date of the log entry. Defaults to None.
            docfile (Optional[str], optional): The specific sub file within the document. Defaults to None.
                eg : ["data.oxd","vec.oxd",".index"]
            where={"metadata_key": "value"},
            where_data={"in_data":"search_string"} ,

        Returns:
            List[dict]: The log entries matching the criteria.
        """
        if docfile not in ["data.oxd", "vec.oxd", ".index"]:
            raise ValueError(
                f"""ox-db : docfile should be ["data.oxd","vec.oxd",".index"] not {docfile} """
            )

        all_none = all(var is None for var in [key, uid, time, date, where, where_data])

        log_entries = {}
        if all_none:
            content = self._retrive_doc_all(docfile)
            for uidx, unit in content.items():
                log_entries[uidx] = unit
            return log_entries

        if uid is not None:
            uids = strorlist_to_list(uid)

            if docfile == ".index":

                content = self.doc_index
                for uidx in uids:
                    if uidx in content:
                        unit = content[uidx]
                        log_entries[uidx] = unit
                return log_entries
            else:
                return self._pull_oxd_by_uid(uids, docfile)

        if any([key, time, date, where]):
            uids = self.search_uid(key, time, date, where)
            log_entries_data = self.pull(uid=uids, docfile=docfile)
            return log_entries_data

    def _pull_oxd_by_uid(self, uids, docfile):
        log_entries = {}
        oxd_doc = self.vec_oxd if docfile == "vec.oxd" else self.data_oxd
        for uidx in uids:
            unit = oxd_doc.get(uidx)
            if not unit:
                continue
            log_entries[uidx] = unit
        return log_entries

    def search(
        self,
        query: str,
        topn: int = 10,
        log_entries: Optional[List[dict]] = None,
        by: Optional[str] = "dp",
        uid: uids = None,
        key: Optional[str] = None,
        time: Optional[str] = None,
        date: Optional[str] = None,
        where: Optional[dict] = None,
        where_data: Optional[dict] = None,
        includes: Optional[list] = ["uid", "data", "description"],
    ) -> List[dict]:
        """
        Searches log entries based on a query and retrieves the top matching results.

        Args:
            query (str): The search query.
            topn (int, optional): Number of top results to return. Defaults to 10.
            uid (uids, optional): The unique ID(s) of the log entry. Defaults to None.
            key (Optional[str], optional): The key of the log entry. Defaults to None.
            time (Optional[str], optional): The time of the log entry. Defaults to None.
            date (Optional[str], optional): The date of the log entry. Defaults to None.
            where={"metadata_key": "value"},
            log_entries (Optional[List[dict]], optional): The log entry [{"uid":uid,unit:{"data":data,"description":description}}]  Defaults to None.
            by (Optional[str], optional): method of search
                dp : Dot Product (default)
                ed : Euclidean Distance
                cs : Cosine Similarity


        Returns:
            List[dict]: The log entries matching the search query.
        """
        vec_log_entries = log_entries or self.pull(
            uid, key, time, date, docfile="vec.oxd", where=where
        )
        dataset_uids = list(vec_log_entries.keys())
        dataset = list(vec_log_entries.values())
        top_idx = self.vec.search(query, dataset, topn=topn, by=by)
        search_res = {
            "entries": 0,
            "uid": [],
            "data": [],
            "description": [],
            "index": [],
            "embeddings": [],
        }
        if len(top_idx) == 0:
            return search_res

        uids = []
        embeddings = []

        for idx in top_idx:
            uids.append(dataset_uids[idx])
            embeddings.append(dataset[idx])

        res_len = len(uids)
        search_res["entries"] = res_len
        search_res["uid"] = uids
        if "embeddings" in includes:
            search_res["embeddings"] = embeddings

        data_log_entries = self.pull(uid=uids)
        index_log_entries = self.pull(uid=uids, docfile=".index")

        res_data = list(data_log_entries.values())
        res_index = list(index_log_entries.values())

        search_res["index"] = res_index

        for i in range(res_len):
            search_res["data"].append(res_data[i]["data"])
            search_res["description"].append(res_data[i]["description"])

        return search_res

    def show(
        self,
        key: Optional[str] = None,
        uid: uids = None,
        time: Optional[str] = None,
        doc: Optional[str] = None,
        date: Optional[str] = None,
    ):
        # Placeholder for future implementation
        pass

    def embed_all(self, doc: str):
        # Placeholder for future implementation
        pass

    def load_index(self) -> dict:
        """
        Loads data from a BSON or JSON file.

        Returns:
            dict: The loaded data.
        """

        try:
            with open(self.doc_index_path, "rb+") as file:
                file_content = file.read()
                content = bson.decode_all(file_content)[0] if file_content else {}
                self.doc_reg = content["doc_reg"]
                self.doc_index = content["index"]
                return content

        except FileNotFoundError:
            content = {"doc_reg": {"entry": 0}, "index": {}}
            self.doc_reg = content["doc_reg"]
            self.doc_index = content["index"]
            self.save_index()
            return content

    def save_index(self):
        """
        Saves data to a BSON or JSON file.
        """

        log_file_path = self.doc_index_path

        content = {"doc_reg": self.doc_reg, "index": self.doc_index}

        def write_file(file, content):
            file.seek(0)
            file.truncate()
            file.write(bson.encode(content))

        try:
            mode = "rb+"
            with open(log_file_path, mode) as file:
                write_file(file, content)
        except FileNotFoundError:
            mode = "wb"
            with open(log_file_path, mode) as file:
                write_file(file, content)

    def push_index(self, uid: str, index_unit: Any, log_file: str):
        """
        Pushes data to a specified log file.

        Args:
            uid (str): The unique ID for the log entry.
            data (Any): The data to be logged.
            log_file (str): The log file name.
        """
        if index_unit == "" or index_unit is None:
            raise ValueError("ox-db: No data provided for logging")
        self.doc_index[uid] = index_unit
        self.doc_reg["entry"] += 1
        self.save_index()

    def _retrive_doc_all(self, docfile) -> dict:
        """
        Retrieves all the content key value pairs as dict

        Args:
        docfile (Optional[str], optional): The specific file within the document. Defaults to None.
            eg : ["data.oxd","vec.oxd",".index"]

        Returns:
            dict: dict of the docfile
        """
        content = {}
        if docfile == ".index":
            content = self.doc_index
        elif docfile == "vec.oxd":
            content = self.vec_oxd.load_data()
        else:
            content = self.data_oxd.load_data()
        return content

    def search_uid(
        self,
        key: Optional[str] = None,
        time: Optional[str] = None,
        date: Optional[str] = None,
        where: Optional[dict] = None,
    ) -> List[str]:
        """
        Searches for UIDs based on key, time, or date.

        Args:
            key (Optional[str], optional): The key to search. Defaults to None.
            time (Optional[str], optional): The time to search. Defaults to None.
            date (Optional[str], optional): The date to search. Defaults to None.
            where={"metadata_key": "value"}.
        Returns:
            List[str]: The matching UIDs.
        """

        content = self.doc_index
        uids = []

        for uid, data in content.items():
            log_it = (
                (key == data["key"] if key else True)
                and (self._metadata_filter(where, data["metadata"]) if where else True)
                and (self._match_time(time, data["time"]) if time else True)
                and (self._match_date(date, data["date"]) if date else True)
            )

            if log_it:
                uids.append(uid)

        return uids

    @staticmethod
    def _metadata_filter(query_dict: dict, data_dict: dict):
        """
        Checks if atlest one key-value pair from the query_dict is present in the data_dict

        Args:
            query_dictd dict :  key-value
            data_dict dict :  key-value

        Returns:
            True if atlest one key-value pair or query_dict present in data_dict
        """
        if data_dict is None:
            return False
        for key in query_dict.keys():
            if query_dict[key] == data_dict.get(key):
                return True
        return False

    @staticmethod
    def _match_time(query_time: str, log_time: str) -> bool:
        """
        Checks if the log time matches the query time.

        Args:
            log_time (str): The log time.
            query_time (List[Optional[str]]): The query time components.

        Returns:
            bool: Whether the log time matches the query time.
        """
        log_time_parts = log_time.split(":")
        query_time = query_time.split(":")
        return log_time_parts[: len(query_time)] == query_time

    @staticmethod
    def _match_date(query_date: str, log_date: str) -> bool:
        """
        Checks if the log date matches the query date.

        Args:
            log_date (str): The log date.
            query_date (List[Optional[str]]): The query date components.

        Returns:
            bool: Whether the log date matches the query date.
        """
        query_date = query_date.split("-")
        log_date_parts = log_date.split("-")
        return log_date_parts[: len(query_date)] == query_date
