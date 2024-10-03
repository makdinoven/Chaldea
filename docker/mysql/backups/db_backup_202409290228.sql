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
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
INSERT INTO `alembic_version` VALUES ('4e034ec5512c');
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

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
  `stamina` int DEFAULT NULL,
  `energy` int DEFAULT NULL,
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
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `character_attributes`
--

LOCK TABLES `character_attributes` WRITE;
/*!40000 ALTER TABLE `character_attributes` DISABLE KEYS */;
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
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `character_inventory`
--

LOCK TABLES `character_inventory` WRITE;
/*!40000 ALTER TABLE `character_inventory` DISABLE KEYS */;
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
  KEY `ix_character_requests_id` (`id`),
  KEY `ix_character_requests_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `character_requests`
--

LOCK TABLES `character_requests` WRITE;
/*!40000 ALTER TABLE `character_requests` DISABLE KEYS */;
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
) ENGINE=InnoDB AUTO_INCREMENT=29 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `character_skills`
--

LOCK TABLES `character_skills` WRITE;
/*!40000 ALTER TABLE `character_skills` DISABLE KEYS */;
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `characters`
--

LOCK TABLES `characters` WRITE;
/*!40000 ALTER TABLE `characters` DISABLE KEYS */;
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

INSERT INTO `classes` VALUES (1,'Воин',NULL),(2,'Ловкач',NULL),(3,'Маг',NULL);

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
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `equipment_slots`
--

LOCK TABLES `equipment_slots` WRITE;
/*!40000 ALTER TABLE `equipment_slots` DISABLE KEYS */;
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
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_items_name` (`name`),
  KEY `ix_items_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `items`
--

LOCK TABLES `items` WRITE;
/*!40000 ALTER TABLE `items` DISABLE KEYS */;
INSERT INTO `items` VALUES (1,'frrr',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0),(2,'efrrrd',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0),(3,'frrrd',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0),(4,'erwer',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0),(5,'erwfrer',NULL,0,NULL,1.00,'grgrrrrrrrrrrr',0,NULL,0);
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
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
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
INSERT INTO `races` VALUES (1,'Человек','Самая многочисленная раса Лока. Проживают повсеместно – в основном за пределами Халдеи. Имеют многочисленные государства, основанные ими же – Союзная  Империя, Винланд, Ямато, Вотчина, Сарма, и прочие. Отличаются своей приспосабливаемостью и относительно недолгим, но насыщенным сроком жизни. Люди разделены на множество разных народов, которые отличаются своей культурой и другими особенностями. '),(2,'Эльф','Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста. '),(3,'Драконид','Потомки драконов, начиная с третьего поколения, дракониды являются гуманоидной расой, количество представителей которой очень мало. Лучше людей во всём – имеют более долгий срок жизни, чуть выше ростом, часто могут иметь чешую и крылья, или же другие атрибуты, которые остались им от драконьих предков. Делятся на равагарт и рорис – два народа, что происходят из Ямато, или же Иймора.'),(4,'Дворф','Коренастый низкорослый народ, что отличается своим относительно низким ростом (до 140 сантиметров) и мышечной массой, а также долгим сроком жизни (до 200 лет). Дворфы в основном живут в глубинах Халдеи близ горных хребтов, или  под ними. Одна из немногочисленных рас, которая тем не менее – встречается повсеместно как в Харбизе, так и в других странах. Знаменитые ремесленники и воины. '),(5,'Демон','Коренной народ Халдеи, который сейчас населяет в основном – собственное государство Кроймага. Отличается гуманоидными чертами, которые существенно искажаются. Демоны – самая долгоживущая раса Ло-Ка, они могут жить до 500 лет, а чаще всего и вообще не сталкиваются с естественной смертью от старости. Разделяются на два вида – альбы и левиафаны. '),(6,'Бистмен','Зверораса, гуманоиды, что имеют отличительные звериные черты. Обычно имеют человеческий срок жизни, чуть выше остальных гуманоидов, как эльфы или люди. Ведут своё происхождение почти всегда – из собственной страны на юге Халдеи, Тулунгу. Могут отличаться тем, на какой вид зверей больше похожи, что не влияет на их возможность размножения. '),(7,'Урук','Некогда варварский народ, что населяет восток Халдеи и Берег Ножей, в итоге основав государства Улус и одноимённую региону страну – Берег Ножей. Отличаются очень коротким сроком жизни (до 40 лет), высоким ростом (до 250 сантиметров) и особыми чертами лица и цветом кожи. Разделяются на северных уруков, и тёмных уруков. ');
/*!40000 ALTER TABLE `races` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skills`
--

DROP TABLE IF EXISTS `skills`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skills` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `description` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skills`
--

LOCK TABLES `skills` WRITE;
/*!40000 ALTER TABLE `skills` DISABLE KEYS */;
/*!40000 ALTER TABLE `skills` ENABLE KEYS */;
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
INSERT INTO `subraces` VALUES (1,1,'Норды','Семейство народов севера, к которым относят имперцев, варангов, юрлен, портуциан и другие мелкие народы, которые родственные им. Отличаются светлым цветом кожи, обычным ростом, от 160 до 180 сантиметров, разнообразным цветом глаз и волос. Населяют в основном Союзную Империю, Вотчину, Патриду, Винланд, но часто встречаются и в других регионах. '),(2,1,'Ост','Южное семейство народов, самое малочисленное и отдалённое от основных центров человеческой цивилизации. Темнокожие и коренастые, осты обычно крупнее своих соплеменников-людей, отличаются оттенками кожи от светло-коричневого – до брунатного чёрного, тёмными волосами. Осты ведут своё происхождение из островов Сарма, к ним относится народ сармусар. '),(3,1,'Ориентал','Восточная островная группа человеческой расы. Отделившись от основного массива, они населяют острова Ямато, крупный остров Чжао и мелкие острова Штормового Океана. Отличаются более низким ростом, чем соплеменники, особым разрезом глаз и оттенком кожи. К ним относятся народы кай, иято и моко, что населяют Ямато, а также народ чжао и мин, что населяют Юнь Чжао. '),(4,2,'Лесной','Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы. '),(5,2,'Темный','Второй ортодоксальный народ эльфов, который чаще всего сохраняет традиции предков. Ведут своё происхождение с болотистых мрачных земель Гносты, на западе от Альбины. Отличаются тёмной кожей, оттенки которой могут варьироваться от светло-серой до брунатной. Часто встречаются красные и фиолетовые оттенки глаз. Тёмные эльфы за пределами Гносты – беженцы, или потомки оных.'),(6,2,'Малах','Самый многочисленных народ эльфов, который отошёл от традиций изоляции. Ведут своё присхождение в основном из Малахии, своего национального государства. Могут отличаться смуглой кожей, более низким ростом, чем у своих соплеменников, и готовностью к сотрудничеству. Они – прирождённые торговцы и дипломаты. '),(7,3,'Равагарт','Восточный народ драконидов, что населяют остров Иято и очень плотно связаны с этим народом Ямато. Отличаются узким разрезом глаз и кровными связями с представителями Ямато, чуть более низким ростом. Равагарт  часто встречаются в других странах мира, странствуя в поисках своего места в жизни. '),(8,3,'Рорис','Южный народ драконидов, который ведёт своё происхождение из государства Иймор, и плотно связан со своими предками-драконами, поклоняясь им. Ближе всего к человеческой группе нордов – от чего часто имеют их внешние качества, в виде светлой кожи и обычной формы глаз. Немногочисленные, но от того не менее распространённые. '),(9,4,'Золотой','Золотые дворфы отличаются светлым цветом кожи, своей приверженность к кочевому образу жизни, а также многочисленностью. Они составляют основу народа нахарбиз, а также их часто можно встретить в рядах купцов и торговцев. Мужчины золотых дворфов имеют традиции отращивать длинные бороды, а женщины – отращивать волосы. '),(10,4,'Ониксовый','Потомки народа проклятых, которые смогли освободиться от своих оков проклятия, южные дворфы из Чёрных Гор, что некогда давно отделились от основной массы золотых. Отличаются тёмным цветом кожи, от смуглых оттенков, до серого или брунатного. Ониксовые дворфы встречаются редко, но известны как свирепые бойцы. '),(11,5,'Левиафан','Те, в ком осталось больше демонической крови, что находит это в своих проявлениях. Левиафаны – более похожи на зверей, чем на гуманоидов, могут отличаться явными демоническими признаками, и не похожи на людей или эльфов внешне – у них могут быть больше клыки, да и само их тело – крупнее. Не редкость – дополнительные пары конечностей и костяные наросты. '),(12,5,'Альб','Более гуманоидные демоны, часто могут быть не выше двух метров ростом, похожи на людей внешней, но имея те или иные «демонические черты», такие как рога, хвост, красный цвет кожи, повсеместная чешуя, особый цвет глаз – прочая. Потомки первичных демонов и гуманоидных рас. Самый распространённый вид демонов.'),(13,6,'Зверолюд','Настоящие бистмены, что напоминают антропоморфных животных, в которых фактически нет человеческих черт, кроме ровной походки и общей схожести силуэта. Они могут напоминать хищников или травоядных, отличаться окрасом, наличием меха или перьев, но всегда больше напоминают зверей, чем остальных гуманоидов. Населяют Тулунгу и редко встречаются за пределами своей страны. '),(14,6,'Полукровка','Результат скрещивания зверолюдей с гуманоидными расами людей и эльфов. Полукровки – больше напоминают своих гуманоидных предков, но всё также сохраняют разные животные черты, будь то наличие хвоста, особой формы ушей, меха, когтей, перьев или чего ещё угодно, что досталось им в наследство от зверолюда-предка. Обычно ниже зверолюдов, и живут меньше – но часто сотрудничают с другими расами. '),(15,7,'Северный','Основной народ уруков, которых чаще всего встречают представители других рас. Отличаются относительно светлой кожей, от серой до оттенков зелёного, но без перегиба в тёмные цвета, традициями отращивать длинные косы и готовностью сотрудничать с другими расами. Северные уруки населяют Улус, своё государство, и часто встречаются в других странах, а также укладают семьи с людьми и эльфами.'),(16,7,'Темный','Южный, более дикий народ уруков, который населил жестокие земли Берега Ножа. Более коренастые, тёмные уруки в первую очередь отличаются тёмным цветом кожи, от тёмно-зелёного до брунатно-коричневого, а также своим свирепым характером. Почти не покидают своих родных земель, но могут отправиться в далёкие странствия в поисках славы. ');
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
  `registered_at` datetime DEFAULT NULL,
  `role` varchar(100) DEFAULT NULL,
  `avatar` varchar(255) DEFAULT NULL,
  `balance` int DEFAULT NULL,
  `id_character` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_users_username` (`username`),
  UNIQUE KEY `ix_users_email` (`email`),
  KEY `ix_users_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (6,'superadmin@mail.ru','admin','admin',NULL,'admin',NULL,NULL,NULL),(7,'user@mail.ru','user','user',NULL,'user',NULL,NULL,NULL);
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2024-09-28 23:28:52
