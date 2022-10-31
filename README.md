# bu-class-finder

A Python Selenium script which scrapes BU's course portal for specific classes and sends a notification via Telegram bot when a class is open.

Deployed to Heroku.

---
## Technical Details
Database is a MongoDB Atlas cluster.

Each document in the collection has the following schema:

* _id: ObjectId
* name: String
* users: String[]
