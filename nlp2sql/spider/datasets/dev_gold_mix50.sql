SELECT pettype ,  weight FROM pets ORDER BY pet_age LIMIT 1	pets_1
SELECT name ,  country FROM singer WHERE song_name LIKE '%Hey%'	concert_singer
SELECT count(*) FROM CARS_DATA WHERE YEAR  =  1980;	car_1
SELECT avg(age) ,  min(age) ,  max(age) FROM singer WHERE country  =  'France'	concert_singer
SELECT count(DISTINCT pettype) FROM pets	pets_1
select max(mpg) from cars_data where cylinders  =  8 or year  <  1980	car_1
SELECT count(*) FROM pets WHERE weight  >  10	pets_1
SELECT T1.horsepower FROM CARS_DATA AS T1 ORDER BY T1.accelerate DESC LIMIT 1;	car_1
SELECT name ,  capacity FROM stadium ORDER BY average DESC LIMIT 1	concert_singer
SELECT avg(age) ,  min(age) ,  max(age) FROM singer WHERE country  =  'France'	concert_singer
SELECT weight FROM pets ORDER BY pet_age LIMIT 1	pets_1
SELECT count(*) FROM CARS_DATA WHERE YEAR  =  1980;	car_1
SELECT count(DISTINCT pettype) FROM pets	pets_1
select distinct year from cars_data where weight between 3000 and 4000;	car_1
SELECT DISTINCT country FROM singer WHERE age  >  20	concert_singer
SELECT petid ,  weight FROM pets WHERE pet_age  >  1	pets_1
select avg(capacity) ,  max(capacity) from stadium	concert_singer
SELECT count(*) FROM CARS_DATA WHERE horsepower  >  150;	car_1
SELECT count(*) FROM pets WHERE weight  >  10	pets_1
SELECT count(*) FROM CARS_DATA WHERE Cylinders  >  4;	car_1
SELECT name ,  capacity FROM stadium ORDER BY average DESC LIMIT 1	concert_singer
SELECT name ,  country FROM singer WHERE song_name LIKE '%Hey%'	concert_singer
SELECT count(*) FROM CONTINENTS;	car_1
SELECT pettype ,  weight FROM pets ORDER BY pet_age LIMIT 1	pets_1
SELECT weight FROM pets ORDER BY pet_age LIMIT 1	pets_1
SELECT song_name ,  song_release_year FROM singer ORDER BY age LIMIT 1	concert_singer
select min(weight) from cars_data where cylinders  =  8 and year  =  1974	car_1
SELECT petid ,  weight FROM pets WHERE pet_age  >  1	pets_1
select max(capacity), average from stadium	concert_singer
SELECT count(*) FROM CONTINENTS;	car_1
SELECT T2.petid FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid WHERE T1.Lname  =  'Smith'	pets_1
SELECT count(*) FROM CAR_MAKERS AS T1 JOIN COUNTRIES AS T2 ON T1.Country  =  T2.CountryId WHERE T2.CountryName  =  'france';	car_1
SELECT YEAR FROM concert GROUP BY YEAR ORDER BY count(*) DESC LIMIT 1	concert_singer
SELECT avg(pet_age) ,  max(pet_age) ,  pettype FROM pets GROUP BY pettype	pets_1
SELECT count(*) FROM MODEL_LIST AS T1 JOIN CAR_MAKERS AS T2 ON T1.Maker  =  T2.Id JOIN COUNTRIES AS T3 ON T2.Country  =  T3.CountryId WHERE T3.CountryName  =  'usa';	car_1
SELECT country ,  count(*) FROM singer GROUP BY country	concert_singer
SELECT T2.name ,  T2.capacity FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id  =  T2.stadium_id WHERE T1.year  >=  2014 GROUP BY T2.stadium_id ORDER BY count(*) DESC LIMIT 1	concert_singer
SELECT max(weight) ,  petType FROM pets GROUP BY petType	pets_1
SELECT T2.horsepower ,  T1.Make FROM CAR_NAMES AS T1 JOIN CARS_DATA AS T2 ON T1.MakeId  =  T2.Id WHERE T2.cylinders  =  3 ORDER BY T2.horsepower DESC LIMIT 1;	car_1
SELECT Count(*) ,  T2.FullName ,  T2.id FROM MODEL_LIST AS T1 JOIN CAR_MAKERS AS T2 ON T1.Maker  =  T2.Id GROUP BY T2.id;	car_1
SELECT count(*) FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid WHERE T1.age  >  20	pets_1
SELECT T2.concert_name ,  T2.theme ,  count(*) FROM singer_in_concert AS T1 JOIN concert AS T2 ON T1.concert_id  =  T2.concert_id GROUP BY T2.concert_id	concert_singer
select t2.name ,  t2.capacity from concert as t1 join stadium as t2 on t1.stadium_id  =  t2.stadium_id where t1.year  >  2013 group by t2.stadium_id order by count(*) desc limit 1	concert_singer
SELECT T1.CountryName FROM COUNTRIES AS T1 JOIN CONTINENTS AS T2 ON T1.Continent  =  T2.ContId JOIN CAR_MAKERS AS T3 ON T1.CountryId  =  T3.Country WHERE T2.Continent  =  'europe' GROUP BY T1.CountryName HAVING count(*)  >=  3;	car_1
SELECT DISTINCT T1.fname ,  T1.age FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid	pets_1
SELECT stuid FROM student EXCEPT SELECT T1.stuid FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'cat'	pets_1
SELECT name FROM stadium WHERE stadium_id NOT IN (SELECT stadium_id FROM concert)	concert_singer
SELECT T2.Make ,  T1.Year FROM CARS_DATA AS T1 JOIN CAR_NAMES AS T2 ON T1.Id  =  T2.MakeId WHERE T1.Year  =  (SELECT min(YEAR) FROM CARS_DATA);	car_1
SELECT name FROM stadium EXCEPT SELECT T2.name FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id  =  T2.stadium_id WHERE T1.year  =  2014	concert_singer
select t1.fname from student as t1 join has_pet as t2 on t1.stuid  =  t2.stuid join pets as t3 on t3.petid  =  t2.petid where t3.pettype  =  'cat' intersect select t1.fname from student as t1 join has_pet as t2 on t1.stuid  =  t2.stuid join pets as t3 on t3.petid  =  t2.petid where t3.pettype  =  'dog'	pets_1
