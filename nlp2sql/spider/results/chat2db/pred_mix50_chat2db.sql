SELECT PetType, weight FROM Pets ORDER BY pet_age ASC LIMIT 1
SELECT Name, Country FROM singer WHERE Song_Name LIKE '%Hey%'
SELECT COUNT(*) FROM cars_data WHERE Year = 1980
SELECT AVG(Age), MIN(Age), MAX(Age) FROM singer WHERE Country = 'France'
SELECT COUNT(DISTINCT PetType) FROM Pets
SELECT MAX(MPG) FROM cars_data WHERE Cylinders = 8 OR Year < 1980
SELECT COUNT(*) FROM Pets WHERE weight > 10
SELECT Horsepower FROM cars_data ORDER BY Accelerate DESC LIMIT 1
SELECT Name, Capacity FROM stadium ORDER BY Average DESC LIMIT 1
SELECT AVG(Age), MIN(Age), MAX(Age) FROM singer WHERE Country = 'France'
SELECT weight FROM Pets WHERE PetType = 'dog' ORDER BY pet_age ASC LIMIT 1
SELECT COUNT(*) FROM cars_data WHERE Year = 1980
SELECT COUNT(DISTINCT PetType) FROM Pets
SELECT DISTINCT T1.Year FROM cars_data AS T1 WHERE T1.Weight < 4000 AND T1.Year IN (SELECT Year FROM cars_data WHERE Weight > 3000)
SELECT DISTINCT Country FROM singer WHERE Age > 20
SELECT PetID, weight FROM Pets WHERE pet_age > 1
SELECT AVG(Capacity), MAX(Capacity) FROM stadium
SELECT COUNT(*) FROM cars_data WHERE Horsepower > 150
SELECT COUNT(*) FROM Pets WHERE weight > 10
SELECT COUNT(*) FROM cars_data WHERE Cylinders > 4
SELECT Name, Capacity FROM stadium ORDER BY Average DESC LIMIT 1
SELECT Name, Country FROM singer WHERE Song_Name LIKE '%Hey%'
SELECT COUNT(*) FROM continents
SELECT PetType, weight FROM Pets ORDER BY pet_age ASC LIMIT 1
SELECT weight FROM Pets WHERE PetType = 'dog' ORDER BY pet_age ASC LIMIT 1
SELECT Name, Song_release_year FROM singer ORDER BY Age ASC LIMIT 1
SELECT MIN(Weight) FROM cars_data WHERE Cylinders = 8 AND Year = 1974
SELECT PetID, weight FROM Pets WHERE pet_age > 1
SELECT MAX(Capacity), AVG(Capacity) FROM stadium
SELECT COUNT(*) FROM continents
SELECT T2.PetID FROM Student AS T1 JOIN Has_Pet AS T3 ON T1.StuID = T3.StuID JOIN Pets AS T2 ON T3.PetID = T2.PetID WHERE T1.LName = 'Smith'
SELECT COUNT(*) FROM car_makers AS T1 JOIN countries AS T2 ON T1.Country = T2.CountryId WHERE T2.CountryName = 'france'
SELECT Year FROM concert GROUP BY Year ORDER BY COUNT(*) DESC LIMIT 1
SELECT AVG(pet_age), MAX(pet_age), PetType FROM Pets GROUP BY PetType
SELECT COUNT(*) FROM model_list AS T1 JOIN car_makers AS T2 ON T1.Maker = T2.Id JOIN countries AS T3 ON T2.Country = T3.CountryId WHERE T3.CountryName = 'usa'
SELECT Country, COUNT(*) FROM singer GROUP BY Country
SELECT T1.Name, T1.Capacity FROM stadium AS T1 JOIN concert AS T2 ON T1.Stadium_ID = T2.Stadium_ID WHERE T2.Year >= 2014 GROUP BY T1.Stadium_ID ORDER BY COUNT(*) DESC LIMIT 1
SELECT MAX(weight), PetType FROM Pets GROUP BY PetType
SELECT T1.Horsepower, T2.Make FROM cars_data AS T1 JOIN car_names AS T2 ON T1.Id = T2.MakeId WHERE T1.Cylinders = 3 ORDER BY T1.Horsepower DESC LIMIT 1
SELECT COUNT(T1.ModelId), T2.Id, T2.FullName FROM model_list AS T1 JOIN car_makers AS T2 ON T1.Maker = T2.Id GROUP BY T2.Id, T2.FullName
SELECT COUNT(*) FROM Pets AS T1 JOIN Has_Pet AS T2 ON T1.PetID = T2.PetID JOIN Student AS T3 ON T2.StuID = T3.StuID WHERE T3.Age > 20
SELECT T1.concert_Name, T1.Theme, COUNT(T2.Singer_ID) FROM concert AS T1 JOIN singer_in_concert AS T2 ON T1.concert_ID = T2.concert_ID GROUP BY T1.concert_ID
SELECT T1.Name, T1.Capacity FROM stadium AS T1 JOIN concert AS T2 ON T1.Stadium_ID = T2.Stadium_ID WHERE T2.Year > 2013 GROUP BY T1.Stadium_ID ORDER BY COUNT(*) DESC LIMIT 1
SELECT T2.CountryName, COUNT(*) FROM car_makers AS T1 JOIN countries AS T2 ON T1.Country = T2.CountryId JOIN continents AS T3 ON T2.Continent = T3.ContId WHERE T3.Continent = 'europe' GROUP BY T2.CountryName HAVING COUNT(*) >= 3
SELECT DISTINCT T1.Fname, T1.Age FROM Student AS T1 JOIN Has_Pet AS T2 ON T1.StuID = T2.StuID
SELECT StuID FROM Student WHERE StuID NOT IN (SELECT T1.StuID FROM Has_Pet AS T1 JOIN Pets AS T2 ON T1.PetID = T2.PetID WHERE T2.PetType = 'cat')
SELECT Name FROM stadium WHERE Stadium_ID NOT IN (SELECT Stadium_ID FROM concert)
SELECT T2.Make, T1.Year FROM cars_data AS T1 JOIN car_names AS T2 ON T1.Id = T2.MakeId WHERE T1.Year = (SELECT MIN(Year) FROM cars_data)
SELECT Name FROM stadium WHERE Stadium_ID NOT IN (SELECT T1.Stadium_ID FROM stadium AS T1 JOIN concert AS T2 ON T1.Stadium_ID = T2.Stadium_ID WHERE T2.Year = 2014)
SELECT T1.Fname FROM Student AS T1 JOIN Has_Pet AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.PetType = 'cat' AND T1.StuID IN (SELECT T1.StuID FROM Student AS T1 JOIN Has_Pet AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.PetType = 'dog')
