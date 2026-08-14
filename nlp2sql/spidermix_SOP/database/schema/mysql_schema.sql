-- Spider Mix50 三库结构：以 2026-08-13 本机 MySQL 快照为准。
-- 仅建库建表，不删除已有对象、不导入数据、不创建账号。

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS `pets_1`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE `pets_1`;

CREATE TABLE IF NOT EXISTS `Student` (
  `StuID` int NOT NULL,
  `LName` varchar(100) NOT NULL,
  `Fname` varchar(100) NOT NULL,
  `Age` int NOT NULL,
  `Sex` char(1) NOT NULL,
  `Major` int NOT NULL,
  `Advisor` int NOT NULL,
  `city_code` varchar(10) NOT NULL,
  PRIMARY KEY (`StuID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `Pets` (
  `PetID` int NOT NULL,
  `PetType` varchar(50) NOT NULL,
  `pet_age` int NOT NULL,
  `weight` decimal(10,2) NOT NULL,
  PRIMARY KEY (`PetID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `Has_Pet` (
  `StuID` int NOT NULL,
  `PetID` int NOT NULL,
  PRIMARY KEY (`StuID`, `PetID`),
  CONSTRAINT `fk_has_pet_student` FOREIGN KEY (`StuID`) REFERENCES `Student` (`StuID`),
  CONSTRAINT `fk_has_pet_pet` FOREIGN KEY (`PetID`) REFERENCES `Pets` (`PetID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `concert_singer`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE `concert_singer`;

CREATE TABLE IF NOT EXISTS `stadium` (
  `Stadium_ID` int NOT NULL,
  `Location` varchar(150) NOT NULL,
  `Name` varchar(150) NOT NULL,
  `Capacity` int NOT NULL,
  `Highest` int NOT NULL,
  `Lowest` int NOT NULL,
  `Average` int NOT NULL,
  PRIMARY KEY (`Stadium_ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `singer` (
  `Singer_ID` int NOT NULL,
  `Name` varchar(150) NOT NULL,
  `Country` varchar(100) NOT NULL,
  `Song_Name` varchar(150) NOT NULL,
  `Song_release_year` int NOT NULL,
  `Age` int NOT NULL,
  `Is_male` char(1) NOT NULL,
  PRIMARY KEY (`Singer_ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `concert` (
  `concert_ID` int NOT NULL,
  `concert_Name` varchar(150) NOT NULL,
  `Theme` varchar(150) NOT NULL,
  `Stadium_ID` int NOT NULL,
  `Year` int NOT NULL,
  PRIMARY KEY (`concert_ID`),
  CONSTRAINT `fk_concert_stadium` FOREIGN KEY (`Stadium_ID`) REFERENCES `stadium` (`Stadium_ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `singer_in_concert` (
  `concert_ID` int NOT NULL,
  `Singer_ID` int NOT NULL,
  PRIMARY KEY (`concert_ID`, `Singer_ID`),
  CONSTRAINT `fk_sic_concert` FOREIGN KEY (`concert_ID`) REFERENCES `concert` (`concert_ID`),
  CONSTRAINT `fk_sic_singer` FOREIGN KEY (`Singer_ID`) REFERENCES `singer` (`Singer_ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `car_1`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE `car_1`;

CREATE TABLE IF NOT EXISTS `continents` (
  `ContId` int NOT NULL,
  `Continent` varchar(100) NOT NULL,
  PRIMARY KEY (`ContId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `countries` (
  `CountryId` int NOT NULL,
  `CountryName` varchar(100) NOT NULL,
  `Continent` int NOT NULL,
  PRIMARY KEY (`CountryId`),
  CONSTRAINT `fk_country_continent` FOREIGN KEY (`Continent`) REFERENCES `continents` (`ContId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `car_makers` (
  `Id` int NOT NULL,
  `Maker` varchar(100) NOT NULL,
  `FullName` varchar(150) NOT NULL,
  `Country` int NOT NULL,
  PRIMARY KEY (`Id`),
  CONSTRAINT `fk_maker_country` FOREIGN KEY (`Country`) REFERENCES `countries` (`CountryId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `model_list` (
  `ModelId` int NOT NULL,
  `Maker` int NOT NULL,
  `Model` varchar(100) NOT NULL,
  PRIMARY KEY (`ModelId`),
  CONSTRAINT `fk_model_maker` FOREIGN KEY (`Maker`) REFERENCES `car_makers` (`Id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `car_names` (
  `MakeId` int NOT NULL,
  `Model` varchar(100) NOT NULL,
  `Make` varchar(200) NOT NULL,
  PRIMARY KEY (`MakeId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `cars_data` (
  `Id` int NOT NULL,
  `MPG` decimal(10,2) DEFAULT NULL,
  `Cylinders` int NOT NULL,
  `Edispl` decimal(10,2) NOT NULL,
  `Horsepower` int DEFAULT NULL,
  `Weight` int NOT NULL,
  `Accelerate` decimal(10,2) NOT NULL,
  `Year` int NOT NULL,
  PRIMARY KEY (`Id`),
  CONSTRAINT `fk_cars_name` FOREIGN KEY (`Id`) REFERENCES `car_names` (`MakeId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

