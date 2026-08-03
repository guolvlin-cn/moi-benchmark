SELECT `PetType` AS `宠物类型`,`pet_age` AS `年龄`,`weight` AS `体重` FROM `pets` ORDER BY `pet_age` LIMIT 1
SELECT `Name` AS `歌手姓名`,`Country` AS `国籍` FROM `singer` WHERE `Song_Name` LIKE '%Hey%'
SELECT COUNT(1) AS `1980年汽车数量` FROM `cars_data` WHERE `Year`=1980
SELECT AVG(`Age`) AS `平均年龄`,MIN(`Age`) AS `最小年龄`,MAX(`Age`) AS `最大年龄` FROM `singer` WHERE `Country`='France'
SELECT COUNT(DISTINCT `PetType`) AS `宠物类型数量` FROM `pets`
SELECT MAX(CAST(`MPG` AS DOUBLE)) AS `最大MPG` FROM `cars_data` WHERE (`Cylinders`=8 OR `Year`<1980) AND `MPG` IS NOT NULL AND `MPG`!=''
SELECT COUNT(1) AS `体重超过10的宠物数量` FROM `pets` WHERE `weight`>10
SELECT `Horsepower`, `Accelerate` FROM `cars_data` ORDER BY `Accelerate` DESC LIMIT 1
SELECT `Name` AS `体育场名称`,`Capacity` AS `容量`,`Average` AS `平均上座率` FROM `stadium` ORDER BY `Average` DESC LIMIT 1
SELECT AVG(`Age`) AS `平均年龄`,MIN(`Age`) AS `最小年龄`,MAX(`Age`) AS `最大年龄` FROM `singer` WHERE `Country`='France'
SELECT `weight` AS `体重` FROM `pets` WHERE `PetType`='dog' ORDER BY `pet_age` LIMIT 1
SELECT COUNT(1) AS `1980年汽车数量` FROM `cars_data` WHERE `Year`=1980
SELECT COUNT(DISTINCT `PetType`) AS `宠物类型数量` FROM `pets`
SELECT `Year` AS `年份` FROM `cars_data` WHERE `Weight`<4000 GROUP BY `Year` INTERSECT SELECT `Year` AS `年份` FROM `cars_data` WHERE `Weight`>3000 GROUP BY `Year` ORDER BY `年份`
SELECT DISTINCT `Country` AS `国家` FROM `singer` WHERE `Age`>20 ORDER BY `Country`
SELECT `PetID` AS `宠物ID`,`weight` AS `体重` FROM `pets` WHERE `pet_age`>1
SELECT AVG(`Capacity`) AS `平均容量`,MAX(`Capacity`) AS `最大容量` FROM `stadium`
SELECT COUNT(1) AS `马力大于150的车辆数` FROM `cars_data` WHERE CAST(`Horsepower` AS DOUBLE)>150
SELECT COUNT(1) AS `体重超过10的宠物数量` FROM `pets` WHERE `weight`>10
SELECT COUNT(1) AS `超过4缸的汽车数量` FROM `cars_data` WHERE `Cylinders`>4
SELECT `Name` AS `体育场名称`,`Capacity` AS `容量`,`Average` AS `平均上座率` FROM `stadium` ORDER BY `Average` DESC LIMIT 1
SELECT `Name` AS `姓名`,`Country` AS `国家` FROM `singer` WHERE `Song_Name` LIKE '%Hey%'
SELECT COUNT(1) AS `大洲数量` FROM `continents`
SELECT `PetType` AS `宠物类型`,`pet_age` AS `年龄`,`weight` AS `体重` FROM `pets` ORDER BY `pet_age` LIMIT 1
SELECT `weight` AS `体重` FROM `pets` WHERE `PetType`='dog' ORDER BY `pet_age` LIMIT 1
SELECT `Song_Name` AS `歌曲名称`,`Song_release_year` AS `发行年份` FROM `singer` WHERE `Age`=(SELECT MIN(`Age`) FROM `singer`)
SELECT MIN(`Weight`) AS `最小重量` FROM `cars_data` WHERE `Cylinders`=8 AND `Year`=1974
SELECT `PetID` AS `宠物ID`,`weight` AS `体重` FROM `pets` WHERE `pet_age`>1
SELECT MAX(`Capacity`) AS `最大容量`,AVG(`Capacity`) AS `平均容量` FROM `stadium`
SELECT COUNT(1) AS `大洲数量` FROM `continents`
SELECT `h`.`PetID` AS `宠物ID` FROM `has_pet` AS `h` JOIN `student` AS `s` ON `h`.`StuID`=`s`.`StuID` WHERE `s`.`LName`='Smith'
SELECT `c`.`CountryName` AS `国家`,COUNT(1) AS `制造商数量` FROM `car_makers` AS `cm` JOIN `countries` AS `c` ON `cm`.`Country`=`c`.`CountryId` GROUP BY `c`.`CountryName` ORDER BY `制造商数量` DESC
SELECT `Year`,COUNT(1) AS `音乐会数量` FROM `concert` GROUP BY `Year` ORDER BY `音乐会数量` DESC LIMIT 1
SELECT `PetType` AS `宠物类型`,AVG(`pet_age`) AS `平均年龄`,MAX(`pet_age`) AS `最大年龄` FROM `pets` GROUP BY `PetType`
SELECT COUNT(1) AS `美国生产车型数量` FROM (`model_list` AS `ml` JOIN `car_makers` AS `cm` ON `ml`.`Maker`=`cm`.`Id`) JOIN `countries` AS `c` ON `cm`.`Country`=`c`.`CountryId` WHERE `c`.`CountryName`='usa'
SELECT `Country` AS `国家`,COUNT(1) AS `歌手数量` FROM `singer` GROUP BY `Country` ORDER BY `歌手数量` DESC
SELECT `s`.`Name` AS `体育场名称`,`s`.`Capacity` AS `容量`,COUNT(`c`.`concert_ID`) AS `演唱会数量` FROM `concert` AS `c` JOIN `stadium` AS `s` ON `c`.`Stadium_ID`=`s`.`Stadium_ID` WHERE CAST(`c`.`Year` AS SIGNED)>=2014 GROUP BY `c`.`Stadium_ID`,`s`.`Name`,`s`.`Capacity` ORDER BY `演唱会数量` DESC LIMIT 1
SELECT `PetType` AS `宠物类型`,MAX(`weight`) AS `最大体重` FROM `pets` GROUP BY `PetType`
SELECT `cn`.`Make` AS `品牌`,`cd`.`Horsepower` AS `马力` FROM `cars_data` AS `cd` JOIN `car_names` AS `cn` ON `cd`.`Id`=`cn`.`MakeId` WHERE `cd`.`Cylinders`=3 ORDER BY CAST(`cd`.`Horsepower` AS SIGNED) DESC LIMIT 1
-- ERROR ConnectionError
SELECT COUNT(`hp`.`PetID`) AS `宠物数量` FROM `has_pet` AS `hp` JOIN `student` AS `s` ON `hp`.`StuID`=`s`.`StuID` WHERE `s`.`Age`>20
SELECT `c`.`concert_Name` AS `演唱会名称`,`c`.`Theme` AS `主题`,COUNT(`s`.`Singer_ID`) AS `歌手数量` FROM `concert` AS `c` LEFT JOIN `singer_in_concert` AS `s` ON `c`.`concert_ID`=`s`.`concert_ID` GROUP BY `c`.`concert_ID`,`c`.`concert_Name`,`c`.`Theme`
SELECT `s`.`Name` AS `体育场名称`,`s`.`Capacity` AS `容量`,COUNT(`c`.`concert_ID`) AS `演唱会数量` FROM `concert` AS `c` JOIN `stadium` AS `s` ON `c`.`Stadium_ID`=`s`.`Stadium_ID` WHERE CAST(`c`.`Year` AS SIGNED)>2013 GROUP BY `c`.`Stadium_ID`,`s`.`Name`,`s`.`Capacity` ORDER BY `演唱会数量` DESC LIMIT 1
SELECT `c`.`CountryName` AS `国家名称`,COUNT(`cm`.`Id`) AS `制造商数量` FROM (`car_makers` AS `cm` JOIN `countries` AS `c` ON `cm`.`Country`=`c`.`CountryId`) JOIN `continents` AS `ct` ON `c`.`Continent`=`ct`.`ContId` WHERE `ct`.`Continent`='europe' GROUP BY `c`.`CountryName` HAVING COUNT(`cm`.`Id`)>=3 ORDER BY `制造商数量` DESC
SELECT DISTINCT `s`.`Fname` AS `名字`,`s`.`Age` AS `年龄` FROM `student` AS `s` JOIN `has_pet` AS `hp` ON `s`.`StuID`=`hp`.`StuID` ORDER BY `s`.`Fname`,`s`.`Age`
SELECT `StuID` AS `学生ID` FROM `student` WHERE `StuID` NOT IN (SELECT `h`.`StuID` FROM `has_pet` AS `h` JOIN `pets` AS `p` ON `h`.`PetID`=`p`.`PetID` WHERE `p`.`PetType`='cat')
SELECT `s`.`Name` AS `体育场名称` FROM `stadium` AS `s` LEFT JOIN `concert` AS `c` ON `s`.`Stadium_ID`=`c`.`Stadium_ID` WHERE `c`.`Stadium_ID` IS NULL
SELECT `cm`.`Maker` AS `制造商`,`c`.`Year` AS `生产年份` FROM ((`cars_data` AS `c` JOIN `car_names` AS `cn` ON `c`.`Id`=`cn`.`MakeId`) JOIN `model_list` AS `ml` ON `cn`.`MakeId`=`ml`.`ModelId`) JOIN `car_makers` AS `cm` ON `ml`.`Maker`=`cm`.`Id` WHERE `c`.`Year`=1970 LIMIT 1
SELECT `s`.`Name` AS `体育场名称` FROM `stadium` AS `s` WHERE `s`.`Stadium_ID` NOT IN (SELECT `c`.`Stadium_ID` FROM `concert` AS `c` WHERE `c`.`Year`='2014') ORDER BY `s`.`Name`
SELECT `s`.`Fname` AS `名字`,GROUP_CONCAT(DISTINCT `p`.`PetType` SEPARATOR ',') AS `宠物类型` FROM (`student` AS `s` JOIN `has_pet` AS `hp` ON `s`.`StuID`=`hp`.`StuID`) JOIN `pets` AS `p` ON `hp`.`PetID`=`p`.`PetID` GROUP BY `s`.`StuID`,`s`.`Fname`
