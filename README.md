# RoamlyService

Backend Service that talks to database

We can use Postman or something to test these endpoints

Make sure to use pyEnv 3.11 or below (not 3.12 since some libraries dont have the support for it)

To make a post request
curl -X POST "http://192.168.1.78:8000/add-property/" \
-H "Content-Type: application/json" \
-d '{
"name": "Rodeo Drive",
"city": "Los Angeles",
"country": "USA",
"mediumResponseIndiaCarsShopping": "Ah, Rodeo Drive—the very name conjures images of opulence, gleaming storefronts, and luxury cars prowling its three iconic blocks in Beverly Hills. But did you know that this world-famous shopping haven wasn’t always a temple of glamour? Long before designer boutiques and exotic sports cars ruled the scene, Rodeo Drive was little more than a dusty patch of land where ranchers herded cattle. The name \"Rodeo\" actually nods to its humble beginnings, inspired by the Spanish word _ro-deh-oh_, meaning “roundup.”\n\nFast-forward to the early 20th century, and the transformation began. Beverly Hills itself was born from the dream of wealthy investors who imagined a utopia for the affluent. Rodeo Drive became its crown jewel, steadily attracting luxury brands eager to bask in the glow of Hollywood glamour. By the 1960s and ‘70s, thanks to the booming entertainment industry, the street hit its stride as a playground for movie stars and moguls. Think of it as the set where the rich and famous mingled with the world’s most exclusive labels—Chanel, Gucci, and Prada among them.\n\nHere’s a fun tidbit: the legendary Bijan Boutique, once dubbed “the most expensive store in the world,” still operates on Rodeo Drive. Visitors were welcomed by appointment only, and even browsing meant brushing shoulders with royalty and A-list celebrities. Shah Rukh Khan fans might be tickled to know he’s likely visited while filming or vacationing in LA. And for car lovers? Bijan’s store features one of the most photographed driveways in the city, adorned with customized luxury cars like Bugattis and Rolls-Royces—a subtle nod to India’s long-standing appreciation for show-stopping vehicles.\n\nThe architecture of Rodeo Drive deserves its own applause. The cobblestoned side street known as Two Rodeo blends European elegance with California charm, complete with a splash of old-world Italian flair. It’s like walking through a film set—a vibe reminiscent of lavish Bollywood music videos. And speaking of cinema, Rodeo Drive starred in _Pretty Woman,_ where Julia Roberts’ character triumphantly reinvents herself in high fashion. Picture her strutting past shop windows; it’s a vibe not unlike those unforgettable montages in _Zindagi Na Milegi Dobara_.\n\nOf course, this grandeur comes at a price. Real estate on Rodeo Drive is some of the most expensive in the world, with rents soaring into hundreds of thousands of dollars monthly for prime storefronts. The street is meticulously managed by the Rodeo Drive Committee, a group of retailers who ensure it remains pristine and buzzing with events, such as the holiday lighting ceremonies and car shows featuring Lamborghinis, Ferraris, and the occasional McLaren—a treat for any auto enthusiast.\n\nToday, Rodeo Drive remains a magnet for global tourists, including many from India, where luxury shopping is gaining popularity. Don’t worry if you’re just window shopping; the energy of Rodeo is as enchanting as any shopping spree. My tip? Take a leisurely stroll, savor a latte at a nearby café, and soak in the spectacle. Who knows, you might even spot your favorite Bollywood star cruising by in a Rolls-Royce."
}'

uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Add user for POST Request
curl -X POST "http://192.168.1.78:8000/register-user/" \
-H "Content-Type: application/json" \
-d '{
"name": "Vboo",
"email": "vaibhavgargpgw@gmail.com",
"country": "USA",
"interestOne": "Biking",
"interestTwo": "Driving",
"interestThree": "Shopping",
"age": "5"
}'
