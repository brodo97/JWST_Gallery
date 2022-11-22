CREATE TABLE "News" (
	"ID"	TEXT NOT NULL,
	"Title"	TEXT,
	"Description"	TEXT,
	"ImageURL"	TEXT,
	"Link"	TEXT,
	"Sent"	INTEGER DEFAULT 0,
	PRIMARY KEY("ID")
)