SELECT pettype, weight FROM Pets ORDER BY pet_age ASC, petid ASC LIMIT 1
SELECT name, country FROM singer WHERE LOWER(song_name) LIKE '%hey%' ORDER BY name
SELECT COUNT(*) AS car_count FROM cars_data WHERE year = 1980
SELECT AVG(age) AS avg_age, MIN(age) AS min_age, MAX(age) AS max_age FROM singer WHERE LOWER(country) = 'france'
SELECT COUNT(DISTINCT pettype) AS pet_type_count FROM Pets
SELECT MAX(CAST(mpg AS REAL)) AS max_mpg FROM cars_data WHERE cylinders = 8 OR year < 1980
SELECT COUNT(*) AS pet_count FROM Pets WHERE weight > 10
SELECT horsepower FROM cars_data ORDER BY accelerate DESC, id ASC LIMIT 1
SELECT name, capacity FROM stadium ORDER BY average DESC, stadium_id ASC LIMIT 1
SELECT AVG(age) AS avg_age, MIN(age) AS min_age, MAX(age) AS max_age FROM singer WHERE LOWER(country) = 'france'
SELECT weight FROM Pets WHERE LOWER(pettype) = 'dog' ORDER BY pet_age ASC, petid ASC LIMIT 1
SELECT COUNT(*) AS car_count FROM cars_data WHERE year = 1980
SELECT COUNT(DISTINCT pettype) AS pet_type_count FROM Pets
SELECT year FROM cars_data GROUP BY year HAVING MIN(weight) < 4000 AND MAX(weight) > 3000 ORDER BY year
SELECT DISTINCT country FROM singer WHERE age > 20 ORDER BY country
SELECT petid, weight FROM Pets WHERE pet_age > 1 ORDER BY petid
SELECT AVG(capacity) AS avg_capacity, MAX(capacity) AS max_capacity FROM stadium
SELECT COUNT(*) AS car_count FROM cars_data WHERE CAST(horsepower AS REAL) > 150
SELECT COUNT(*) AS pet_count FROM Pets WHERE weight > 10
SELECT COUNT(*) AS car_count FROM cars_data WHERE cylinders > 4
SELECT name, capacity FROM stadium ORDER BY average DESC, stadium_id ASC LIMIT 1
SELECT name, country FROM singer WHERE LOWER(song_name) LIKE '%hey%' ORDER BY name
SELECT COUNT(*) AS continent_count FROM continents
SELECT pettype, weight FROM Pets ORDER BY pet_age ASC, petid ASC LIMIT 1
SELECT weight FROM Pets WHERE LOWER(pettype) = 'dog' ORDER BY pet_age ASC, petid ASC LIMIT 1
SELECT name, song_release_year FROM singer ORDER BY age ASC, singer_id ASC LIMIT 1
SELECT MIN(weight) AS min_weight FROM cars_data WHERE cylinders = 8 AND year = 1974
SELECT petid, weight FROM Pets WHERE pet_age > 1 ORDER BY petid
SELECT AVG(capacity) AS avg_capacity, MAX(capacity) AS max_capacity FROM stadium
SELECT COUNT(*) AS continent_count FROM continents
SELECT DISTINCT hp.petid FROM Student s JOIN Has_Pet hp ON s.stuid = hp.stuid WHERE LOWER(s.lname) = 'smith' ORDER BY hp.petid
SELECT COUNT(*) AS maker_count FROM car_makers cm JOIN countries c ON cm.country = c.countryid WHERE LOWER(c.countryname) = 'france'
SELECT year, COUNT(*) AS concert_count FROM concert GROUP BY year ORDER BY concert_count DESC, year ASC LIMIT 1
SELECT pettype, AVG(pet_age) AS avg_age, MAX(pet_age) AS max_age FROM Pets GROUP BY pettype ORDER BY pettype
SELECT COUNT(*) AS model_count FROM model_list ml JOIN car_makers cm ON ml.maker = cm.id JOIN countries c ON cm.country = c.countryid WHERE LOWER(c.countryname) = 'usa'
SELECT country, COUNT(*) AS singer_count FROM singer GROUP BY country ORDER BY country
SELECT s.name, s.capacity, COUNT(*) AS concert_count FROM concert c JOIN stadium s ON c.stadium_id = s.stadium_id WHERE c.year >= 2014 GROUP BY s.stadium_id, s.name, s.capacity ORDER BY concert_count DESC, s.stadium_id ASC LIMIT 1
SELECT pettype, MAX(weight) AS max_weight FROM Pets GROUP BY pettype ORDER BY pettype
SELECT cn.make, MAX(SAFE_CAST(cd.horsepower AS FLOAT64)) AS max_horsepower FROM cars_data cd JOIN car_names cn ON cd.id = cn.makeid WHERE cd.cylinders = 3 GROUP BY cn.make ORDER BY max_horsepower DESC, cn.make ASC LIMIT 1
SELECT cm.id, cm.fullname, COUNT(ml.modelid) AS model_count FROM car_makers cm LEFT JOIN model_list ml ON cm.id = ml.maker GROUP BY cm.id, cm.fullname ORDER BY cm.id
SELECT COUNT(*) AS pet_count FROM Student s JOIN Has_Pet hp ON s.stuid = hp.stuid WHERE s.age > 20
SELECT c.concert_name, c.theme, COUNT(sic.singer_id) AS singer_count FROM concert c LEFT JOIN singer_in_concert sic ON c.concert_id = sic.concert_id GROUP BY c.concert_id, c.concert_name, c.theme ORDER BY c.concert_id
SELECT s.name, s.capacity, COUNT(*) AS concert_count FROM concert c JOIN stadium s ON c.stadium_id = s.stadium_id WHERE c.year > 2013 GROUP BY s.stadium_id, s.name, s.capacity ORDER BY concert_count DESC, s.stadium_id ASC LIMIT 1
SELECT c.countryname, COUNT(cm.id) AS maker_count FROM countries c JOIN continents ct ON c.continent = ct.contid JOIN car_makers cm ON cm.country = c.countryid WHERE LOWER(ct.continent) = 'europe' GROUP BY c.countryid, c.countryname HAVING COUNT(cm.id) >= 3 ORDER BY c.countryname
SELECT DISTINCT s.fname, s.age FROM Student s JOIN Has_Pet hp ON s.stuid = hp.stuid ORDER BY s.fname, s.age
SELECT s.stuid FROM Student s WHERE NOT EXISTS (SELECT 1 FROM Has_Pet hp JOIN Pets p ON hp.petid = p.petid WHERE hp.stuid = s.stuid AND LOWER(p.pettype) = 'cat') ORDER BY s.stuid
SELECT s.name FROM stadium s WHERE NOT EXISTS (SELECT 1 FROM concert c WHERE c.stadium_id = s.stadium_id) ORDER BY s.name
SELECT cn.make, cd.year FROM cars_data cd JOIN car_names cn ON cd.id = cn.makeid WHERE cd.year = (SELECT MIN(year) FROM cars_data) ORDER BY cn.makeid
SELECT s.name FROM stadium s WHERE NOT EXISTS (SELECT 1 FROM concert c WHERE c.stadium_id = s.stadium_id AND c.year = 2014) ORDER BY s.name
SELECT s.fname FROM Student s JOIN Has_Pet hp ON s.stuid = hp.stuid JOIN Pets p ON hp.petid = p.petid WHERE LOWER(p.pettype) IN ('cat', 'dog') GROUP BY s.stuid, s.fname HAVING COUNT(DISTINCT LOWER(p.pettype)) = 2 ORDER BY s.fname
