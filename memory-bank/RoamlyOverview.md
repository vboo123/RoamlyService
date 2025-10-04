Detailed information on Roamly app to be used as context when using cursor so it understands the application. Include any high level design diagrams and flows so it know what we are implementing. Per feature, create a new detailed markdown file to help provide accurate use cases. 


## What is Roamly?

Roamly is an AI powered tour guide app that helps travelers explore the city they are in. They are able to integrate Roamly with different apps and sources to help us learn about them. They can launch custom tour guides and configure several parameters so we can produce high-quality, personalized tours from any location. The app will help recommend local events, transportation, food, etc based off their preferences and their in-app interactions as we learn more and more about them. 

## How will it be organized?

We will curate and build a traveler persona for each traveler, all at different levels of the application. At the highest level will be

Traveler Persona —> Trip Level Persona —> Custom Tour Guide. 

These will be dynamically updated at different points based on app integrations and user interactions. Overtime, as the user does more and more trips, the persona will mature and become a more accurate representation of the user. 

[Traveler Persona](https://www.notion.so/Traveler-Persona-2500319c82cd80e7abf5cbb968eb6965?pvs=21)

[Trip Level Persona](https://www.notion.so/Trip-Level-Persona-2650319c82cd807180eaf74eb30c2a25?pvs=21)

[Custom Tour Guide](https://www.notion.so/Custom-Tour-Guide-2570319c82cd802cb838cbe6efd6de4e?pvs=21)


```json
+---------------------+              +-------------------------+
|     RoamlyUI        |              |   External Integrations |
|  (Frontend: iOS/JS) |              |  (HealthKit, Calendar,  |
|---------------------|              |   Weather, Bookings)    |
| - Onboarding Quiz   |              +-------------------------+
| - Trip Creation     |
| - Tour Guide Setup  |
| - Live Tour Mode    |
+----------+----------+
           |
           v
+-------------------------+
|     RoamlyService       |   (Backend API Layer)
|-------------------------|
| - Auth / Users          |
| - CRUD Trips/Tours      |
| - Stores Persona Links  |
| - Calls Recommendation  |
+---+-------------+-------+
    |             |
    v             v
+---------+   +-------------------+
| DynamoDB|   |        S3         |
| (Traveler|   | (Trip/Tour JSONs)|
| Persona) |   |   (Snapshots)    |
+---------+   +-------------------+
     ^
     |
     v
+-------------------------+
| RoamlyRecommendationEng |
|-------------------------|
| - Input: Traveler + Trip|
|   Persona + Context     |
| - Logic: ML / Rules /   |
|   Hybrid Algorithms     |
| - Output: Rec. Routes,  |
|   Tour Prefills, Updates|
+-------------------------+

```


## Backend Design Flow
See roamlyBackendFlow.png in same memory-bank folder to see current UI flow

