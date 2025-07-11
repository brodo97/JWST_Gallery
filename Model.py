from pymongo import MongoClient
from bson.objectid import ObjectId
import logging

LOGGER : logging.Logger = None

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

        LOGGER.info(f"Initializing MongoDB connection to database: {database}, collection: {collection}")
        
        try:
            # Init MongoDB client
            self.client = MongoClient(
                uri,
                tls=True,
                tlsCertificateKeyFile=certificate
            )
            LOGGER.debug("MongoDB client created successfully")

            # Select the correct database
            database = self.client[database]
            # And collection
            self.coll = database[collection]
            LOGGER.info("MongoDB connection established successfully")
            
        except Exception as e:
            LOGGER.error(f"Failed to initialize MongoDB connection: {str(e)}")
            raise

        return

    def get_all_resources(self):
        """
        Function to get all known resources
        :return: An iterable generator containing the list of every known resource as MongoDB documents
        """
        LOGGER.info("Retrieving all resources from database")
        
        try:
            count = 0
            for document in self.coll.find({}, {"Identifier"}):
                count += 1
                yield document.values()
            LOGGER.info(f"Successfully retrieved {count} resources")
            
        except Exception as e:
            LOGGER.error(f"Error retrieving all resources: {str(e)}")
            raise

    def get_unsent_resources(self):
        """
        Function to get all unsent resources
        :return: An iterable generator containing the list of unsent resources as MongoDB documents
        """
        LOGGER.info("Retrieving unsent resources from database")
        
        try:
            count = 0
            for document in self.coll.find({"Sent": 0}, {"Identifier", "Title", "Description", "ImageURL", "Link"}):
                count += 1
                LOGGER.debug(f"Found unsent resource: {document.get('Identifier', 'Unknown')}")
                yield document.values()
            LOGGER.info(f"Successfully retrieved {count} unsent resources")
            
        except Exception as e:
            LOGGER.error(f"Error retrieving unsent resources: {str(e)}")
            raise

    def update_to_sent(self, _id: str, message_id: int):
        """
        Function to update a resource status. It set the Sent parameter to the corresponding Telegram message ID

        :param message_id: Telegram Message ID
        :param _id: MongoDB Unique Document ID

        :return: Execution result
        :rtype: bool
        """

        LOGGER.info(f"Updating resource {_id} to sent status with message ID: {message_id}")
        
        try:
            # Update the value
            result = self.coll.update_one(
                {"_id": ObjectId(_id)},
                {"$set": {"Sent": message_id}}
            )

            success = result.modified_count == 1
            if success:
                LOGGER.info(f"Successfully updated resource {_id} to sent status")
            else:
                LOGGER.warning(f"No documents were modified for resource {_id}. Document may not exist or already have this status.")
            
            return success
            
        except Exception as e:
            LOGGER.error(f"Error updating resource {_id} to sent status: {str(e)}")
            raise

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

        LOGGER.info(f"Inserting new resource: {identifier}")
        LOGGER.debug(f"Resource details - Title: {title}, Image URL: {imageurl}, Link: {link}")
        
        try:
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
            result = self.coll.insert_one(resource)
            
            LOGGER.info(f"Successfully inserted new resource with ID: {result.inserted_id}")
            
        except Exception as e:
            LOGGER.error(f"Error inserting new resource {identifier}: {str(e)}")
            raise

        return

    def close(self):
        """
        Close MongoDB Connection
        :return: None
        """

        LOGGER.info("Closing MongoDB connection")
        
        try:
            self.client.close()
            LOGGER.info("MongoDB connection closed successfully")
        except Exception as e:
            LOGGER.error(f"Error closing MongoDB connection: {str(e)}")
            raise
