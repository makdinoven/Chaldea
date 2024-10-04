-- MySQL dump 10.13  Distrib 8.0.39, for Linux (x86_64)
--
-- Host: localhost    Database: mydatabase
-- ------------------------------------------------------
-- Server version	8.0.39

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `character_attributes`
--

DROP TABLE IF EXISTS `character_attributes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `character_attributes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `character_id` int DEFAULT NULL,
  `health` int DEFAULT NULL,
  `mana` int DEFAULT NULL,
  `energy` int DEFAULT NULL,
  `stamina` int DEFAULT NULL,
  `endurance` int DEFAULT NULL,
  `strength` int DEFAULT NULL,
  `agility` int DEFAULT NULL,
  `intelligence` int DEFAULT NULL,
  `luck` int DEFAULT NULL,
  `charisma` int DEFAULT NULL,
  `damage` int DEFAULT NULL,
  `dodge` int DEFAULT NULL,
  `critical_hit_chance` int DEFAULT NULL,
  `critical_damage` int DEFAULT NULL,
  `res_effects` int DEFAULT NULL,
  `res_physical` int DEFAULT NULL,
  `res_cutting` int DEFAULT NULL,
  `res_crushing` int DEFAULT NULL,
  `res_piersing` int DEFAULT NULL,
  `res_magic` int DEFAULT NULL,
  `res_fire` int DEFAULT NULL,
  `res_ice` int DEFAULT NULL,
  `res_watering` int DEFAULT NULL,
  `res_electricity` int DEFAULT NULL,
  `res_sainting` int DEFAULT NULL,
  `res_wind` int DEFAULT NULL,
  `res_damning` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_character_attributes_character_id` (`character_id`),
  KEY `ix_character_attributes_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `character_attributes`
--

LOCK TABLES `character_attributes` WRITE;
/*!40000 ALTER TABLE `character_attributes` DISABLE KEYS */;
INSERT INTO `character_attributes` (`id`, `character_id`, `health`, `mana`, `energy`, `stamina`, `endurance`, `strength`, `agility`, `intelligence`, `luck`, `charisma`, `damage`, `dodge`, `critical_hit_chance`, `critical_damage`, `res_effects`, `res_physical`, `res_cutting`, `res_crushing`, `res_piersing`, `res_magic`, `res_fire`, `res_ice`, `res_watering`, `res_electricity`, `res_sainting`, `res_wind`, `res_damning`) VALUES (1,1,10,0,10,10,10,20,20,10,10,0,0,5,20,125,0,0,0,0,0,0,0,0,0,0,0,0,0),(2,2,10,0,10,10,10,20,20,10,10,0,0,5,20,125,0,0,0,0,0,0,0,0,0,0,0,0,0),(3,3,10,0,10,10,10,20,20,10,10,0,0,5,20,125,0,0,0,0,0,0,0,0,0,0,0,0,0),(4,4,10,0,10,10,10,20,20,10,10,0,0,5,20,125,0,0,0,0,0,0,0,0,0,0,0,0,0),(5,5,10,0,10,10,10,20,20,10,10,0,0,5,20,125,0,0,0,0,0,0,0,0,0,0,0,0,0),(6,6,10,0,10,10,10,20,20,10,10,0,0,5,20,125,0,0,0,0,0,0,0,0,0,0,0,0,0),(7,7,10,0,10,10,10,20,20,10,10,0,0,5,20,125,0,0,0,0,0,0,0,0,0,0,0,0,0);
/*!40000 ALTER TABLE `character_attributes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `character_inventory`
--

DROP TABLE IF EXISTS `character_inventory`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `character_inventory` (
  `id` int NOT NULL AUTO_INCREMENT,
  `character_id` int NOT NULL,
  `item_id` int NOT NULL,
  `slot_type` enum('bag','armor_slot','weapon_slot','accessory_slot') NOT NULL,
  `quantity` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `item_id` (`item_id`),
  CONSTRAINT `character_inventory_ibfk_1` FOREIGN KEY (`item_id`) REFERENCES `items` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `character_inventory`
--

LOCK TABLES `character_inventory` WRITE;
/*!40000 ALTER TABLE `character_inventory` DISABLE KEYS */;
INSERT INTO `character_inventory` (`id`, `character_id`, `item_id`, `slot_type`, `quantity`) VALUES (1,1,1,'bag',1),(2,1,2,'bag',1),(3,2,1,'bag',1),(4,2,2,'bag',1),(5,3,1,'bag',1),(6,3,2,'bag',1),(7,4,1,'bag',1),(8,4,2,'bag',1),(9,5,1,'bag',1),(10,5,2,'bag',1),(11,6,1,'bag',1),(12,6,2,'bag',1),(13,7,1,'bag',1),(14,7,2,'bag',1);
/*!40000 ALTER TABLE `character_inventory` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `character_requests`
--

DROP TABLE IF EXISTS `character_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `character_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(20) DEFAULT NULL,
  `id_subrace` int DEFAULT NULL,
  `biography` text,
  `personality` text,
  `id_class` int DEFAULT NULL,
  `status` enum('pending','approved','rejected') DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `user_id` int DEFAULT NULL,
  `appearance` text NOT NULL,
  `sex` enum('male','female','genderless') DEFAULT NULL,
  `background` text,
  `age` int DEFAULT NULL,
  `weight` varchar(10) DEFAULT NULL,
  `height` varchar(10) DEFAULT NULL,
  `id_race` int NOT NULL,
  `avatar` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_character_requests_name` (`name`),
  KEY `ix_character_requests_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `character_requests`
--

LOCK TABLES `character_requests` WRITE;
/*!40000 ALTER TABLE `character_requests` DISABLE KEYS */;
INSERT INTO `character_requests` (`id`, `name`, `id_subrace`, `biography`, `personality`, `id_class`, `status`, `created_at`, `user_id`, `appearance`, `sex`, `background`, `age`, `weight`, `height`, `id_race`, `avatar`) VALUES (1,'вавава',1,'вавава','авава',1,'approved','2024-10-03 00:41:36',1,'аавав','male','ававава',34,'34','34',1,''),(2,'strigng',1,'string','string',1,'approved','2024-10-03 00:47:49',1,'string','male','string',0,'string','string',1,'string'),(3,'strigng',1,'string','string',1,'approved','2024-10-03 01:31:49',1,'string','male','string',0,'string','string',1,'string'),(4,'strigng',1,'string','string',1,'approved','2024-10-03 01:31:53',1,'string','male','string',0,'string','string',1,'string'),(5,'strigng',1,'string','string',1,'approved','2024-10-03 01:31:55',1,'string','male','string',0,'string','string',1,'string'),(6,'strigng',1,'string','string',1,'approved','2024-10-03 01:55:49',1,'string','male','string',0,'string','string',1,'string'),(7,'strigng',1,'string','string',1,'approved','2024-10-03 01:55:49',1,'string','male','string',0,'string','string',1,'string'),(8,'strigghng',1,'string','string',1,'pending','2024-10-03 15:15:51',1,'string','male','string',0,'string','string',1,'string');
/*!40000 ALTER TABLE `character_requests` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `character_skills`
--

DROP TABLE IF EXISTS `character_skills`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `character_skills` (
  `id` int NOT NULL AUTO_INCREMENT,
  `character_id` int DEFAULT NULL,
  `skill_1` varchar(100) DEFAULT NULL,
  `skill_2` varchar(100) DEFAULT NULL,
  `skill_3` varchar(100) DEFAULT NULL,
  `skill_4` varchar(100) DEFAULT NULL,
  `skill_5` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_character_skills_character_id` (`character_id`),
  KEY `ix_character_skills_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `character_skills`
--

LOCK TABLES `character_skills` WRITE;
/*!40000 ALTER TABLE `character_skills` DISABLE KEYS */;
INSERT INTO `character_skills` (`id`, `character_id`, `skill_1`, `skill_2`, `skill_3`, `skill_4`, `skill_5`) VALUES (1,1,'Basic Attack','Basic Defense','Basic Heal',NULL,NULL),(2,2,'Basic Attack','Basic Defense','Basic Heal',NULL,NULL),(3,3,'Basic Attack','Basic Defense','Basic Heal',NULL,NULL),(4,4,'Basic Attack','Basic Defense','Basic Heal',NULL,NULL),(5,5,'Basic Attack','Basic Defense','Basic Heal',NULL,NULL),(6,6,'Basic Attack','Basic Defense','Basic Heal',NULL,NULL),(7,7,'Basic Attack','Basic Defense','Basic Heal',NULL,NULL);
/*!40000 ALTER TABLE `character_skills` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `characters`
--

DROP TABLE IF EXISTS `characters`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `characters` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `id_subrace` int NOT NULL,
  `biography` text,
  `personality` text,
  `id_item_inventory` int DEFAULT NULL,
  `id_skill_inventory` int DEFAULT NULL,
  `id_class` int NOT NULL,
  `id_attributes` int DEFAULT NULL,
  `currency_balance` int DEFAULT NULL,
  `request_id` int NOT NULL,
  `user_id` int DEFAULT NULL,
  `appearance` text NOT NULL,
  `sex` enum('male','female','genderless') DEFAULT NULL,
  `background` text,
  `age` int DEFAULT NULL,
  `weight` varchar(10) DEFAULT NULL,
  `height` varchar(10) DEFAULT NULL,
  `id_race` int NOT NULL,
  `avatar` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `request_id` (`request_id`),
  KEY `ix_characters_id` (`id`),
  CONSTRAINT `characters_ibfk_1` FOREIGN KEY (`request_id`) REFERENCES `character_requests` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `characters`
--

LOCK TABLES `characters` WRITE;
/*!40000 ALTER TABLE `characters` DISABLE KEYS */;
INSERT INTO `characters` (`id`, `name`, `id_subrace`, `biography`, `personality`, `id_item_inventory`, `id_skill_inventory`, `id_class`, `id_attributes`, `currency_balance`, `request_id`, `user_id`, `appearance`, `sex`, `background`, `age`, `weight`, `height`, `id_race`, `avatar`) VALUES (1,'вавава',1,'вавава','авава',2,1,1,1,0,1,1,'аавав','male','ававава',34,'34','34',1,'https://storage.googleapis.com/chaldea/profile_photo_1_bfe04deebf094a7ca06b0dd9893a0931.png'),(2,'strigng',1,'string','string',4,2,1,2,0,2,1,'string','male','string',0,'string','string',1,'string'),(3,'strigng',1,'string','string',6,3,1,3,0,3,1,'string','male','string',0,'string','string',1,'string'),(4,'strigng',1,'string','string',8,4,1,4,0,4,1,'string','male','string',0,'string','string',1,'string'),(5,'strigng',1,'string','string',10,5,1,5,0,5,1,'string','male','string',0,'string','string',1,'string'),(6,'strigng',1,'string','string',12,6,1,6,0,6,1,'string','male','string',0,'string','string',1,'string'),(7,'strigng',1,'string','string',14,7,1,7,0,7,1,'string','male','string',0,'string','string',1,'string');
/*!40000 ALTER TABLE `characters` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `classes`
--

DROP TABLE IF EXISTS `classes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `classes` (
  `id_class` int NOT NULL AUTO_INCREMENT,
  `name` varchar(50) NOT NULL,
  `description` text,
  PRIMARY KEY (`id_class`),
  KEY `ix_classes_id_class` (`id_class`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `classes`
--

LOCK TABLES `classes` WRITE;
/*!40000 ALTER TABLE `classes` DISABLE KEYS */;
INSERT INTO `classes` (`id_class`, `name`, `description`) VALUES (1,'Воин','бал'),(2,'Ловкач','ава'),(3,'Маг','папа');
/*!40000 ALTER TABLE `classes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `equipment_slots`
--

DROP TABLE IF EXISTS `equipment_slots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `equipment_slots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `character_id` int NOT NULL,
  `slot_type` enum('head','chest','legs','feet','weapon','accessory') NOT NULL,
  `item_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `item_id` (`item_id`),
  CONSTRAINT `equipment_slots_ibfk_1` FOREIGN KEY (`item_id`) REFERENCES `items` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=43 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `equipment_slots`
--

LOCK TABLES `equipment_slots` WRITE;
/*!40000 ALTER TABLE `equipment_slots` DISABLE KEYS */;
INSERT INTO `equipment_slots` (`id`, `character_id`, `slot_type`, `item_id`) VALUES (1,1,'head',NULL),(2,1,'chest',NULL),(3,1,'legs',NULL),(4,1,'feet',NULL),(5,1,'weapon',NULL),(6,1,'accessory',NULL),(7,2,'head',NULL),(8,2,'chest',NULL),(9,2,'legs',NULL),(10,2,'feet',NULL),(11,2,'weapon',NULL),(12,2,'accessory',NULL),(13,3,'head',NULL),(14,3,'chest',NULL),(15,3,'legs',NULL),(16,3,'feet',NULL),(17,3,'weapon',NULL),(18,3,'accessory',NULL),(19,4,'head',NULL),(20,4,'chest',NULL),(21,4,'legs',NULL),(22,4,'feet',NULL),(23,4,'weapon',NULL),(24,4,'accessory',NULL),(25,5,'head',NULL),(26,5,'chest',NULL),(27,5,'legs',NULL),(28,5,'feet',NULL),(29,5,'weapon',NULL),(30,5,'accessory',NULL),(31,6,'head',NULL),(32,6,'chest',NULL),(33,6,'legs',NULL),(34,6,'feet',NULL),(35,6,'weapon',NULL),(36,6,'accessory',NULL),(37,7,'head',NULL),(38,7,'chest',NULL),(39,7,'legs',NULL),(40,7,'feet',NULL),(41,7,'weapon',NULL),(42,7,'accessory',NULL);
/*!40000 ALTER TABLE `equipment_slots` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `items`
--

DROP TABLE IF EXISTS `items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `items` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) DEFAULT NULL,
  `item_type` enum('axe','armor','flask') DEFAULT NULL,
  `is_stackable` tinyint(1) NOT NULL,
  `max_stack_size` int DEFAULT NULL,
  `weight` decimal(5,2) NOT NULL,
  `description` text,
  `is_sellable` tinyint(1) DEFAULT NULL,
  `price` int DEFAULT NULL,
  `is_rare` tinyint(1) NOT NULL,
  `image` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_items_name` (`name`),
  KEY `ix_items_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `items`
--

LOCK TABLES `items` WRITE;
/*!40000 ALTER TABLE `items` DISABLE KEYS */;
INSERT INTO `items` (`id`, `name`, `item_type`, `is_stackable`, `max_stack_size`, `weight`, `description`, `is_sellable`, `price`, `is_rare`, `image`) VALUES (1,'frrr',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0,NULL),(2,'efrrrd',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0,NULL),(3,'frrrd',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0,NULL),(4,'erwer',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0,NULL),(5,'erwfrer',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0,NULL);
/*!40000 ALTER TABLE `items` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `races`
--

DROP TABLE IF EXISTS `races`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `races` (
  `id_race` int NOT NULL AUTO_INCREMENT,
  `name` varchar(50) NOT NULL,
  `description` text,
  PRIMARY KEY (`id_race`),
  UNIQUE KEY `name` (`name`),
  KEY `ix_races_id_race` (`id_race`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `races`
--

LOCK TABLES `races` WRITE;
/*!40000 ALTER TABLE `races` DISABLE KEYS */;
INSERT INTO `races` (`id_race`, `name`, `description`) VALUES (1,'Человек','Самая многочисленная раса Лока. Проживают повсеместно – в основном за пределами Халдеи. Имеют многочисленные государства, основанные ими же – Союзная  Империя, Винланд, Ямато, Вотчина, Сарма, и прочие. Отличаются своей приспосабливаемостью и относительно недолгим, но насыщенным сроком жизни. Люди разделены на множество разных народов, которые отличаются своей культурой и другими особенностями. '),(2,'Эльф','Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста. '),(3,'Драконид','Потомки драконов, начиная с третьего поколения, дракониды являются гуманоидной расой, количество представителей которой очень мало. Лучше людей во всём – имеют более долгий срок жизни, чуть выше ростом, часто могут иметь чешую и крылья, или же другие атрибуты, которые остались им от драконьих предков. Делятся на равагарт и рорис – два народа, что происходят из Ямато, или же Иймора.'),(4,'Дворф','Коренастый низкорослый народ, что отличается своим относительно низким ростом (до 140 сантиметров) и мышечной массой, а также долгим сроком жизни (до 200 лет). Дворфы в основном живут в глубинах Халдеи близ горных хребтов, или  под ними. Одна из немногочисленных рас, которая тем не менее – встречается повсеместно как в Харбизе, так и в других странах. Знаменитые ремесленники и воины. '),(5,'Демон','Коренной народ Халдеи, который сейчас населяет в основном – собственное государство Кроймага. Отличается гуманоидными чертами, которые существенно искажаются. Демоны – самая долгоживущая раса Ло-Ка, они могут жить до 500 лет, а чаще всего и вообще не сталкиваются с естественной смертью от старости. Разделяются на два вида – альбы и левиафаны. '),(6,'Бистмен','Зверораса, гуманоиды, что имеют отличительные звериные черты. Обычно имеют человеческий срок жизни, чуть выше остальных гуманоидов, как эльфы или люди. Ведут своё происхождение почти всегда – из собственной страны на юге Халдеи, Тулунгу. Могут отличаться тем, на какой вид зверей больше похожи, что не влияет на их возможность размножения. '),(7,'Урук','Некогда варварский народ, что населяет восток Халдеи и Берег Ножей, в итоге основав государства Улус и одноимённую региону страну – Берег Ножей. Отличаются очень коротким сроком жизни (до 40 лет), высоким ростом (до 250 сантиметров) и особыми чертами лица и цветом кожи. Разделяются на северных уруков, и тёмных уруков. ');
/*!40000 ALTER TABLE `races` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `subraces`
--

DROP TABLE IF EXISTS `subraces`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `subraces` (
  `id_subrace` int NOT NULL AUTO_INCREMENT,
  `id_race` int NOT NULL,
  `name` varchar(50) NOT NULL,
  `description` text,
  PRIMARY KEY (`id_subrace`),
  KEY `id_race` (`id_race`),
  KEY `ix_subraces_id_subrace` (`id_subrace`),
  CONSTRAINT `subraces_ibfk_1` FOREIGN KEY (`id_race`) REFERENCES `races` (`id_race`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `subraces`
--

LOCK TABLES `subraces` WRITE;
/*!40000 ALTER TABLE `subraces` DISABLE KEYS */;
INSERT INTO `subraces` (`id_subrace`, `id_race`, `name`, `description`) VALUES (1,1,'Норды','Семейство народов севера, к которым относят имперцев, варангов, юрлен, портуциан и другие мелкие народы, которые родственные им. Отличаются светлым цветом кожи, обычным ростом, от 160 до 180 сантиметров, разнообразным цветом глаз и волос. Населяют в основном Союзную Империю, Вотчину, Патриду, Винланд, но часто встречаются и в других регионах. '),(2,1,'Ост','Южное семейство народов, самое малочисленное и отдалённое от основных центров человеческой цивилизации. Темнокожие и коренастые, осты обычно крупнее своих соплеменников-людей, отличаются оттенками кожи от светло-коричневого – до брунатного чёрного, тёмными волосами. Осты ведут своё происхождение из островов Сарма, к ним относится народ сармусар. '),(3,1,'Ориентал','Восточная островная группа человеческой расы. Отделившись от основного массива, они населяют острова Ямато, крупный остров Чжао и мелкие острова Штормового Океана. Отличаются более низким ростом, чем соплеменники, особым разрезом глаз и оттенком кожи. К ним относятся народы кай, иято и моко, что населяют Ямато, а также народ чжао и мин, что населяют Юнь Чжао. '),(4,2,'Лесной','Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы. '),(5,2,'Темный','Второй ортодоксальный народ эльфов, который чаще всего сохраняет традиции предков. Ведут своё происхождение с болотистых мрачных земель Гносты, на западе от Альбины. Отличаются тёмной кожей, оттенки которой могут варьироваться от светло-серой до брунатной. Часто встречаются красные и фиолетовые оттенки глаз. Тёмные эльфы за пределами Гносты – беженцы, или потомки оных.'),(6,2,'Малах','Самый многочисленных народ эльфов, который отошёл от традиций изоляции. Ведут своё присхождение в основном из Малахии, своего национального государства. Могут отличаться смуглой кожей, более низким ростом, чем у своих соплеменников, и готовностью к сотрудничеству. Они – прирождённые торговцы и дипломаты. '),(7,3,'Равагарт','Восточный народ драконидов, что населяют остров Иято и очень плотно связаны с этим народом Ямато. Отличаются узким разрезом глаз и кровными связями с представителями Ямато, чуть более низким ростом. Равагарт  часто встречаются в других странах мира, странствуя в поисках своего места в жизни. '),(8,3,'Рорис','Южный народ драконидов, который ведёт своё происхождение из государства Иймор, и плотно связан со своими предками-драконами, поклоняясь им. Ближе всего к человеческой группе нордов – от чего часто имеют их внешние качества, в виде светлой кожи и обычной формы глаз. Немногочисленные, но от того не менее распространённые. '),(9,4,'Золотой','Золотые дворфы отличаются светлым цветом кожи, своей приверженность к кочевому образу жизни, а также многочисленностью. Они составляют основу народа нахарбиз, а также их часто можно встретить в рядах купцов и торговцев. Мужчины золотых дворфов имеют традиции отращивать длинные бороды, а женщины – отращивать волосы. '),(10,4,'Ониксовый','Потомки народа проклятых, которые смогли освободиться от своих оков проклятия, южные дворфы из Чёрных Гор, что некогда давно отделились от основной массы золотых. Отличаются тёмным цветом кожи, от смуглых оттенков, до серого или брунатного. Ониксовые дворфы встречаются редко, но известны как свирепые бойцы. '),(11,5,'Левиафан','Те, в ком осталось больше демонической крови, что находит это в своих проявлениях. Левиафаны – более похожи на зверей, чем на гуманоидов, могут отличаться явными демоническими признаками, и не похожи на людей или эльфов внешне – у них могут быть больше клыки, да и само их тело – крупнее. Не редкость – дополнительные пары конечностей и костяные наросты. '),(12,5,'Альб','Более гуманоидные демоны, часто могут быть не выше двух метров ростом, похожи на людей внешней, но имея те или иные «демонические черты», такие как рога, хвост, красный цвет кожи, повсеместная чешуя, особый цвет глаз – прочая. Потомки первичных демонов и гуманоидных рас. Самый распространённый вид демонов.'),(13,6,'Зверолюд','Настоящие бистмены, что напоминают антропоморфных животных, в которых фактически нет человеческих черт, кроме ровной походки и общей схожести силуэта. Они могут напоминать хищников или травоядных, отличаться окрасом, наличием меха или перьев, но всегда больше напоминают зверей, чем остальных гуманоидов. Населяют Тулунгу и редко встречаются за пределами своей страны. '),(14,6,'Полукровка','Результат скрещивания зверолюдей с гуманоидными расами людей и эльфов. Полукровки – больше напоминают своих гуманоидных предков, но всё также сохраняют разные животные черты, будь то наличие хвоста, особой формы ушей, меха, когтей, перьев или чего ещё угодно, что досталось им в наследство от зверолюда-предка. Обычно ниже зверолюдов, и живут меньше – но часто сотрудничают с другими расами. '),(15,7,'Северный','Основной народ уруков, которых чаще всего встречают представители других рас. Отличаются относительно светлой кожей, от серой до оттенков зелёного, но без перегиба в тёмные цвета, традициями отращивать длинные косы и готовностью сотрудничать с другими расами. Северные уруки населяют Улус, своё государство, и часто встречаются в других странах, а также укладают семьи с людьми и эльфами.'),(16,7,'Темный','Южный, более дикий народ уруков, который населил жестокие земли Берега Ножа. Более коренастые, тёмные уруки в первую очередь отличаются тёмным цветом кожи, от тёмно-зелёного до брунатно-коричневого, а также своим свирепым характером. Почти не покидают своих родных земель, но могут отправиться в далёкие странствия в поисках славы. ');
/*!40000 ALTER TABLE `subraces` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `username` varchar(255) NOT NULL,
  `hashed_password` varchar(255) NOT NULL,
  `registered_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `role` varchar(100) DEFAULT 'user',
  `avatar` varchar(255) DEFAULT NULL,
  `balance` int DEFAULT NULL,
  `current_character` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`),
  UNIQUE KEY `username` (`username`),
  KEY `idx_email` (`email`),
  KEY `idx_username` (`username`),
  KEY `current_character` (`current_character`),
  CONSTRAINT `users_ibfk_1` FOREIGN KEY (`current_character`) REFERENCES `characters` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` (`id`, `email`, `username`, `hashed_password`, `registered_at`, `role`, `avatar`, `balance`, `current_character`) VALUES (1,'gui@mail.ru','pass','$2b$12$zjZoTKS9BJbJ4n36Ohu4CeEJZMbRpoy4TGfy4hYhziwkn5uKmA.vC','2024-10-03 00:09:09','user','https://storage.googleapis.com/chaldea/profile_photo_1_52aad9628af7445198b9d5b8d51f4b37.png',NULL,7),(2,'exampаle@mail.ru','user','$2b$12$9kq8rzS.5FuPkHuwU6M/q.k2cQuNgN5t./Sl1XaELy4RYRdyrdRha','2024-10-03 14:50:11','user','assets/avatars/avatar.png',NULL,NULL);
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users_avatar_character_preview`
--

DROP TABLE IF EXISTS `users_avatar_character_preview`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users_avatar_character_preview` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int DEFAULT NULL,
  `avatar` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `users_avatar_character_preview_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users_avatar_character_preview`
--

LOCK TABLES `users_avatar_character_preview` WRITE;
/*!40000 ALTER TABLE `users_avatar_character_preview` DISABLE KEYS */;
INSERT INTO `users_avatar_character_preview` (`id`, `user_id`, `avatar`) VALUES (1,2,'https://storage.googleapis.com/chaldea/profile_photo_1_bfe04deebf094a7ca06b0dd9893a0931.png');
/*!40000 ALTER TABLE `users_avatar_character_preview` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users_avatar_preview`
--

DROP TABLE IF EXISTS `users_avatar_preview`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users_avatar_preview` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int DEFAULT NULL,
  `avatar` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `users_avatar_preview_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users_avatar_preview`
--

LOCK TABLES `users_avatar_preview` WRITE;
/*!40000 ALTER TABLE `users_avatar_preview` DISABLE KEYS */;
INSERT INTO `users_avatar_preview` (`id`, `user_id`, `avatar`) VALUES (1,2,'assets/avatars/avatar.png');
/*!40000 ALTER TABLE `users_avatar_preview` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users_character`
--

DROP TABLE IF EXISTS `users_character`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users_character` (
  `user_id` int NOT NULL,
  `character_id` int NOT NULL,
  PRIMARY KEY (`user_id`,`character_id`),
  KEY `character_id` (`character_id`),
  CONSTRAINT `users_character_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `users_character_ibfk_2` FOREIGN KEY (`character_id`) REFERENCES `characters` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users_character`
--

LOCK TABLES `users_character` WRITE;
/*!40000 ALTER TABLE `users_character` DISABLE KEYS */;
INSERT INTO `users_character` (`user_id`, `character_id`) VALUES (1,4),(1,5),(1,6),(1,7);
/*!40000 ALTER TABLE `users_character` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'mydatabase'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2024-10-04 19:20:35
