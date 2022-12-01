from pymongo import MongoClient
from bson.objectid import ObjectId


class MongoDB():
    """
    Mongo DB Class
    """

    def __init__(self,
                 uri: str,
                 certificate: str,
                 database: str,
                 collection: str):
        """
        Init MongoDB Client and other objects, like COLL (Collection)

        :param uri: MongoDB URI
        :param certificate: MongoDB authentication certificate
        :param database: MongoDB Database Name
        :param collection: Database Collection Name

        :return: None
        """

        # Init MongoDB client
        self.client = MongoClient(
            uri,
            tls=True,
            tlsCertificateKeyFile=certificate
        )

        # Select the correct database
        database = self.client[database]
        # And collection
        self.coll = database[collection]

        return

    def get_all_resources(self):
        """
        Function to get all known resources
        :return: An iterable generator containing the list of every known resource as MongoDB documents
        """
        for document in self.coll.find({}, {"Identifier"}):
            yield document.values()

    def get_unsent_resources(self):
        """
        Function to get all unsent resources
        :return: An iterable generator containing the list of unsent resources as MongoDB documents
        """
        for document in self.coll.find({"Sent": 0}, {"Identifier", "Title", "Description", "ImageURL", "Link"}):
            yield document.values()

    def update_to_sent(self, _id: str, message_id: int):
        """
        Function to update a resource status. It set the Sent parameter to the corresponding Telegram message ID

        :param message_id: Telegram Message ID
        :param _id: MongoDB Unique Document ID

        :return: Execution result
        :rtype: bool
        """

        # Update the value
        result = self.coll.update_one(
            {"_id": ObjectId(_id)},
            {"$set": {"Sent": message_id}}
        )

        return result.modified_count == 1

    def insert_new_resource(self, identifier: str, title: str, description: str, imageurl: str, link: str):
        """
        Function to insert a new resource

        :param identifier: Unique resource identifier in the collection (the resource path)
        :param title: Resource title
        :param description: Resource description
        :param imageurl: Resource image url
        :param link: Resource link

        :return: None
        """

        # Prepare the resource to be inserted
        resource = {
            "Identifier": identifier,
            "Title": title,
            "Description": description,
            "ImageURL": imageurl,
            "Link": link,
            "Sent": 0
        }

        # Update the value
        self.coll.insert_one(
            resource,

        )

        return

    def close(self):
        """
        Close MongoDB Connection
        :return: None
        """

        self.client.close()
