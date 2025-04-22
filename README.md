# Terrier Alert

A Python service that collects class information at Boston University and sends a notification via [Telegram](https://telegram.org/) bot when a class is open.

Deployed on [Render](https://render.com/).

## Demo

![demo](doc/terrier-alert-demo.gif)

### Register Feature (Deprecated)

![register](doc/terrier-alert-register.gif)

## System Design Overview

![system schema](doc/terrier-alert-design-latest.png)

## Technical Details

Database is a MongoDB Atlas Cluster.  
There are two collections: _courses_ and _users_.

Each document in the _courses_ collection has the following schema:

- \_id: `ObjectId`
- name: `String`
- users: `String[]`

Each document in the _users_ collection has the following schema:

- \_id: `ObjectId`
- user: `String`
- last_subscribed: `Date`
- is_subscribed: `Boolean`
- last_subscription: `String`
