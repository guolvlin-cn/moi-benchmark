# MOI Spider Mix50 第一轮评测结果

- 模型：`qwen3.7-plus-2026-05-26`
- 比较方式：MOI 在 MatrixOne 中的原生执行结果，对比 Golden SQL 在本地 MySQL 中的执行结果。
- Execution Accuracy：**40/50 = 80.0%**
- SQL Success Rate：**50/50 = 100.0%**
- 端到端延迟：平均 **17.51s**，P50 **16.11s**，P95 **29.17s**。
- Token：总计 **2,084,012**，平均每题 **41,680**。
- Repeat Correct Rate：本轮只执行 1 次，暂不计算。

## 分项准确率

| 维度 | 正确/总数 | 正确率 |
|---|---:|---:|
| 难度-easy | 26/30 | 86.7% |
| 难度-medium | 10/15 | 66.7% |
| 难度-hard | 4/5 | 80.0% |
| 数据库-car_1 | 12/16 | 75.0% |
| 数据库-concert_singer | 12/17 | 70.6% |
| 数据库-pets_1 | 16/17 | 94.1% |

## 失败题目（10 题）

| 题号 | 难度 | 数据库 | 原因 |
|---|---|---|---|
| mix50_026 | easy | concert_singer | ordered_value_mismatch |
| mix50_027 | easy | car_1 | unordered_value_mismatch |
| mix50_029 | easy | concert_singer | unordered_value_mismatch |
| mix50_030 | easy | car_1 | column_count_mismatch: gold=1 pred=2 |
| mix50_033 | medium | concert_singer | column_count_mismatch: gold=1 pred=2 |
| mix50_037 | medium | concert_singer | column_count_mismatch: gold=2 pred=3 |
| mix50_039 | medium | car_1 | column_count_mismatch: gold=2 pred=3 |
| mix50_043 | medium | concert_singer | column_count_mismatch: gold=2 pred=3 |
| mix50_044 | medium | car_1 | column_count_mismatch: gold=1 pred=2 |
| mix50_050 | hard | pets_1 | column_count_mismatch: gold=1 pred=8 |

## 失败详情

### mix50_026

- 问题：Show the name and the release year of the song by the youngest singer.
- 原因：`ordered_value_mismatch`
- Golden SQL：`SELECT song_name ,  song_release_year FROM singer ORDER BY age LIMIT 1`
- MOI SQL：`SELECT Name, Song_release_year FROM singer ORDER BY Age ASC LIMIT 1`
- Golden 样例：`[["Love", 2016]]`
- MOI 样例：`[["Tribal King", 2016]]`

### mix50_027

- 问题：What is the minimum weight of the car with 8 cylinders produced in 1974 ?
- 原因：`unordered_value_mismatch`
- Golden SQL：`select min(weight) from cars_data where cylinders  =  8 and year  =  1974`
- MOI SQL：`SELECT MIN(Weight) AS MinWeight FROM cars_data WHERE Cylinders = 8 AND Year = 74`
- Golden 样例：`[[4141]]`
- MOI 样例：`[[null]]`

### mix50_029

- 问题：What is the maximum capacity and the average of all stadiums ?
- 原因：`unordered_value_mismatch`
- Golden SQL：`select max(capacity), average from stadium`
- MOI SQL：`SELECT MAX(Capacity) AS Max_Capacity, AVG(Capacity) AS Avg_Capacity FROM stadium`
- Golden 样例：`[[52500, 2106]]`
- MOI 样例：`[[52500, 10621.666666666666]]`

### mix50_030

- 问题：How many continents are there?
- 原因：`column_count_mismatch: gold=1 pred=2`
- Golden SQL：`SELECT count(*) FROM CONTINENTS`
- MOI SQL：`SELECT cm.FullName, COUNT(ml.ModelId) AS model_count
FROM car_makers cm
JOIN model_list ml ON cm.Id = ml.Maker
GROUP BY cm.Id, cm.FullName
ORDER BY model_count DESC
LIMIT 1`
- Golden 样例：`[[5]]`
- MOI 样例：`[["General Motors", 5]]`

### mix50_033

- 问题：Which year has most number of concerts?
- 原因：`column_count_mismatch: gold=1 pred=2`
- Golden SQL：`SELECT YEAR FROM concert GROUP BY YEAR ORDER BY count(*) DESC LIMIT 1`
- MOI SQL：`SELECT Year, COUNT(*) AS concert_count FROM concert GROUP BY Year ORDER BY concert_count DESC LIMIT 1`
- Golden 样例：`[[2014]]`
- MOI 样例：`[[2014, 3]]`

### mix50_037

- 问题：Show the stadium name and capacity with most number of concerts in year 2014 or after.
- 原因：`column_count_mismatch: gold=2 pred=3`
- Golden SQL：`SELECT T2.name ,  T2.capacity FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id  =  T2.stadium_id WHERE T1.year  >=  2014 GROUP BY T2.stadium_id ORDER BY count(*) DESC LIMIT 1`
- MOI SQL：`SELECT T2.Name, T2.Capacity, COUNT(*) AS concert_count
FROM concert AS T1
JOIN stadium AS T2 ON T1.Stadium_ID = T2.Stadium_ID
WHERE T1.Year >= 2014
GROUP BY T2.Stadium_ID, T2.Name, T2.Capacity
ORDER BY concert_count DESC
LIMIT 1`
- Golden 样例：`[["Somerset Park", 11998]]`
- MOI 样例：`[["Somerset Park", 11998, 2]]`

### mix50_039

- 问题：What is the largest amount of horsepower for the models with 3 cylinders and what make is it?
- 原因：`column_count_mismatch: gold=2 pred=3`
- Golden SQL：`SELECT T2.horsepower ,  T1.Make FROM CAR_NAMES AS T1 JOIN CARS_DATA AS T2 ON T1.MakeId  =  T2.Id WHERE T2.cylinders  =  3 ORDER BY T2.horsepower DESC LIMIT 1`
- MOI SQL：`SELECT cd.Horsepower, cm.Maker, cn.Make
FROM cars_data cd
JOIN car_names cn ON cd.Id = cn.MakeId
JOIN model_list ml ON cn.Model = ml.Model
JOIN car_makers cm ON ml.Maker = cm.Id
WHERE cd.Cylinders = 3
ORDER BY cd.Horsepower DESC
LIMIT 5`
- Golden 样例：`[[110, "mazda rx-4"]]`
- MOI 样例：`[[110, "mazda", "mazda rx-4"], [100, "mazda", "mazda rx-7 gs"], [97, "mazda", "mazda rx2 coupe"], [90, "mazda", "mazda rx3"]]`

### mix50_043

- 问题：What is the name and capacity of the stadium with the most concerts after 2013 ?
- 原因：`column_count_mismatch: gold=2 pred=3`
- Golden SQL：`select t2.name ,  t2.capacity from concert as t1 join stadium as t2 on t1.stadium_id  =  t2.stadium_id where t1.year  >  2013 group by t2.stadium_id order by count(*) desc limit 1`
- MOI SQL：`SELECT s.Name, s.Capacity, COUNT(c.concert_ID) AS concert_count
FROM stadium s
JOIN concert c ON s.Stadium_ID = c.Stadium_ID
WHERE c.Year > 2013
GROUP BY s.Stadium_ID, s.Name, s.Capacity
ORDER BY concert_count DESC
LIMIT 1`
- Golden 样例：`[["Somerset Park", 11998]]`
- MOI 样例：`[["Somerset Park", 11998, 2]]`

### mix50_044

- 问题：Which countries in europe have at least 3 car manufacturers?
- 原因：`column_count_mismatch: gold=1 pred=2`
- Golden SQL：`SELECT T1.CountryName FROM COUNTRIES AS T1 JOIN CONTINENTS AS T2 ON T1.Continent  =  T2.ContId JOIN CAR_MAKERS AS T3 ON T1.CountryId  =  T3.Country WHERE T2.Continent  =  'europe' GROUP BY T1.CountryName HAVING count(*)  >=  3`
- MOI SQL：`SELECT c.CountryName, COUNT(cm.Id) AS ManufacturerCount
FROM car_makers cm
JOIN countries c ON cm.Country = c.CountryId
JOIN continents co ON c.Continent = co.ContId
WHERE co.Continent = 'europe'
GROUP BY c.CountryName
HAVING COUNT(cm.Id) >= 3`
- Golden 样例：`[["germany"], ["france"]]`
- MOI 样例：`[["germany", 4], ["france", 3]]`

### mix50_050

- 问题：Find the first name of students who have both cat and dog pets .
- 原因：`column_count_mismatch: gold=1 pred=8`
- Golden SQL：`select t1.fname from student as t1 join has_pet as t2 on t1.stuid  =  t2.stuid join pets as t3 on t3.petid  =  t2.petid where t3.pettype  =  'cat' intersect select t1.fname from student as t1 join has_pet as t2 on t1.stuid  =  t2.stuid join pets as t3 on t3.petid  =  t2.petid where t3.pettype  =  'dog'`
- MOI SQL：`SELECT * FROM pets`
- Golden 样例：`[]`
- MOI 样例：`[[1001, "Smith", "Linda", 18, "F", 600, 1121, "BAL"], [1002, "Kim", "Tracy", 19, "F", 600, 7712, "HKG"], [1003, "Jones", "Shiela", 21, "F", 600, 7792, "WAS"], [1004, "Kumar", "Dinesh", 20, "M", 600, 8423, "CHI"], [1005, "Gompers", "Paul", 26, "M", 600, 1121, "YYZ"]]`
