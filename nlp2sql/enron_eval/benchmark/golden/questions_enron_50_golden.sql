USE `enron_eval`;

-- e01_sender_count
SELECT COUNT(DISTINCT LOWER(TRIM(`from`))) AS sender_count
FROM `enron_emailinfo`
WHERE `from` IS NOT NULL AND TRIM(`from`) <> '';

-- e02_total_emails
SELECT COUNT(DISTINCT `id`) AS total_emails
FROM `enron_emailinfo`;

-- e03_empty_subject
SELECT `id`, `messageid`, `from` AS sender
FROM `enron_emailinfo`
WHERE `subject` IS NULL OR TRIM(`subject`) = ''
ORDER BY `id` ASC;

-- e04_reply_emails
SELECT COUNT(DISTINCT `id`) AS reply_email_count
FROM `enron_emailinfo`
WHERE LOWER(TRIM(`subject`)) LIKE 're:%';

-- e05_phillip_emails
SELECT COUNT(DISTINCT `id`) AS email_count
FROM `enron_emailinfo`
WHERE LOWER(TRIM(`from`)) = 'phillip.allen@enron.com';

-- e06_top10_mailboxes
SELECT TRIM(`mailbox`) AS mailbox, COUNT(DISTINCT `id`) AS email_count
FROM `enron_email`
WHERE `mailbox` IS NOT NULL AND TRIM(`mailbox`) <> ''
GROUP BY TRIM(`mailbox`)
ORDER BY email_count DESC, mailbox ASC
LIMIT 10;

-- e07_sent_mail_count
SELECT COUNT(DISTINCT `id`) AS sent_email_count
FROM `enron_email`
WHERE `mailbox` = 'sent';

-- e08_california_emails
SELECT COUNT(DISTINCT `id`) AS email_count
FROM `enron_emailinfo`
WHERE LOWER(`body`) LIKE '%california%';

-- e09_source_identifiers
SELECT `id`, `source_file_id`, `source_name`
FROM `enron_source`
ORDER BY `id` ASC
LIMIT 10;

-- e10_distinct_mailboxes
SELECT DISTINCT TRIM(`mailbox`) AS mailbox
FROM `enron_email`
WHERE `mailbox` IS NOT NULL AND TRIM(`mailbox`) <> ''
ORDER BY mailbox ASC;

-- e11_latest_emails
WITH parsed AS (
  SELECT
    `id`, `date`, `subject`, `from`,
    STR_TO_DATE(
      REGEXP_SUBSTR(`date`, '^[A-Za-z]{3}, [0-9]{1,2} [A-Za-z]{3} [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}'),
      '%a, %e %b %Y %H:%i:%s'
    ) AS parsed_datetime
  FROM `enron_emailinfo`
)
SELECT `id`, `date`, `subject`, `from` AS sender
FROM parsed
ORDER BY parsed_datetime DESC, `id` DESC
LIMIT 10;

-- e12_2001_email_count
WITH parsed AS (
  SELECT
    `id`,
    STR_TO_DATE(
      REGEXP_SUBSTR(`date`, '^[A-Za-z]{3}, [0-9]{1,2} [A-Za-z]{3} [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}'),
      '%a, %e %b %Y %H:%i:%s'
    ) AS parsed_datetime
  FROM `enron_emailinfo`
)
SELECT COUNT(DISTINCT `id`) AS email_count
FROM parsed
WHERE YEAR(parsed_datetime) = 2001;

-- e13_orig_extended_header_presence
SELECT
  SUM(CASE WHEN `xfrom` IS NOT NULL AND TRIM(`xfrom`) <> '' THEN 1 ELSE 0 END) AS nonempty_xfrom_rows,
  SUM(CASE WHEN `xto` IS NOT NULL AND TRIM(`xto`) <> '' THEN 1 ELSE 0 END) AS nonempty_xto_rows
FROM `enron_emailorig`;

-- e14_people_list
SELECT DISTINCT TRIM(`people`) AS people
FROM `enron_email`
WHERE `people` IS NOT NULL AND TRIM(`people`) <> ''
ORDER BY people ASC;

-- e15_campbell_mailboxes
SELECT COUNT(DISTINCT TRIM(`mailbox`)) AS mailbox_count
FROM `enron_email`
WHERE `people` = 'campbell-l'
  AND `mailbox` IS NOT NULL
  AND TRIM(`mailbox`) <> '';

-- e16_max_mail_count
SELECT MAX(email_count) AS max_email_count
FROM (
  SELECT TRIM(`mailbox`) AS mailbox, COUNT(DISTINCT `id`) AS email_count
  FROM `enron_email`
  WHERE `mailbox` IS NOT NULL AND TRIM(`mailbox`) <> ''
  GROUP BY TRIM(`mailbox`)
) AS mailbox_counts;

-- e17_subject_keyword_meeting
SELECT COUNT(DISTINCT `id`) AS email_count
FROM `enron_emailinfo`
WHERE LOWER(`subject`) LIKE '%meeting%';

-- e18_senders_more_than_100
SELECT LOWER(TRIM(`from`)) AS sender, COUNT(DISTINCT `id`) AS email_count
FROM `enron_emailinfo`
WHERE `from` IS NOT NULL AND TRIM(`from`) <> ''
GROUP BY LOWER(TRIM(`from`))
HAVING COUNT(DISTINCT `id`) > 100
ORDER BY email_count DESC, sender ASC;

-- e19_top_xfrom
SELECT TRIM(`xfrom`) AS xfrom, COUNT(DISTINCT `id`) AS email_count
FROM `enron_emailinfo`
WHERE `xfrom` IS NOT NULL AND TRIM(`xfrom`) <> ''
GROUP BY TRIM(`xfrom`)
ORDER BY email_count DESC, xfrom ASC
LIMIT 10;

-- e20_campbell_source_sequence
SELECT e.`id`, e.`nnn`, i.`subject`, i.`from` AS sender
FROM `enron_email` AS e
JOIN `enron_emailinfo` AS i ON i.`id` = e.`id`
WHERE e.`people` = 'campbell-l'
  AND e.`mailbox` = 'all_documents'
ORDER BY e.`nnn` DESC, e.`id` DESC
LIMIT 10;

-- m01_owner_folder_distribution
SELECT TRIM(`people`) AS people, TRIM(`mailbox`) AS mailbox,
       COUNT(DISTINCT `id`) AS email_count
FROM `enron_email`
WHERE `people` IS NOT NULL AND TRIM(`people`) <> ''
  AND `mailbox` IS NOT NULL AND TRIM(`mailbox`) <> ''
GROUP BY TRIM(`people`), TRIM(`mailbox`)
ORDER BY email_count DESC, people ASC, mailbox ASC;

-- m02_phillip_recipients
SELECT LOWER(TRIM(t.`to`)) AS recipient,
       COUNT(DISTINCT t.`id`) AS email_count
FROM `enron_emailinfo` AS i
JOIN `enron_emailto` AS t ON t.`id` = i.`id`
WHERE LOWER(TRIM(i.`from`)) = 'phillip.allen@enron.com'
  AND t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
GROUP BY LOWER(TRIM(t.`to`))
ORDER BY email_count DESC, recipient ASC
LIMIT 10;

-- m03_california_senders
SELECT LOWER(TRIM(`from`)) AS sender, COUNT(DISTINCT `id`) AS email_count
FROM `enron_emailinfo`
WHERE LOWER(`body`) LIKE '%california%'
  AND `from` IS NOT NULL AND TRIM(`from`) <> ''
GROUP BY LOWER(TRIM(`from`))
ORDER BY email_count DESC, sender ASC
LIMIT 5;

-- m04_employee_source_folders
SELECT TRIM(`xorigin`) AS xorigin,
       COUNT(DISTINCT TRIM(`xfolder`)) AS folder_count
FROM `enron_source`
WHERE `xorigin` IS NOT NULL AND TRIM(`xorigin`) <> ''
  AND `xfolder` IS NOT NULL AND TRIM(`xfolder`) <> ''
GROUP BY TRIM(`xorigin`)
ORDER BY folder_count DESC, xorigin ASC;

-- m05_avg_recipients_per_email
WITH per_email AS (
  SELECT
    i.`id`,
    LOWER(TRIM(i.`from`)) AS sender,
    COUNT(DISTINCT CASE
      WHEN t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
      THEN LOWER(TRIM(t.`to`))
    END) AS recipient_count
  FROM `enron_emailinfo` AS i
  LEFT JOIN `enron_emailto` AS t ON t.`id` = i.`id`
  WHERE i.`from` IS NOT NULL AND TRIM(i.`from`) <> ''
  GROUP BY i.`id`, LOWER(TRIM(i.`from`))
)
SELECT sender, ROUND(AVG(recipient_count), 2) AS avg_recipient_count
FROM per_email
GROUP BY sender
HAVING AVG(recipient_count) > 3
ORDER BY avg_recipient_count DESC, sender ASC;

-- m06_sent_vs_total
SELECT ROUND(
  100.0 * COUNT(DISTINCT CASE WHEN `mailbox` = 'sent' THEN `id` END)
  / NULLIF(COUNT(DISTINCT `id`), 0),
  2
) AS sent_percentage
FROM `enron_email`;

-- m07_most_common_recipient
SELECT LOWER(TRIM(`to`)) AS recipient, COUNT(DISTINCT `id`) AS email_count
FROM `enron_emailto`
WHERE `to` IS NOT NULL AND TRIM(`to`) <> ''
GROUP BY LOWER(TRIM(`to`))
ORDER BY email_count DESC, recipient ASC
LIMIT 1;

-- m08_2001_monthly_trend
WITH parsed AS (
  SELECT
    `id`,
    STR_TO_DATE(
      REGEXP_SUBSTR(`date`, '^[A-Za-z]{3}, [0-9]{1,2} [A-Za-z]{3} [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}'),
      '%a, %e %b %Y %H:%i:%s'
    ) AS parsed_datetime
  FROM `enron_emailinfo`
)
SELECT DATE_FORMAT(parsed_datetime, '%m') AS month,
       COUNT(DISTINCT `id`) AS email_count
FROM parsed
WHERE YEAR(parsed_datetime) = 2001
GROUP BY DATE_FORMAT(parsed_datetime, '%m')
ORDER BY month ASC;

-- m09_allen_folder_emails
SELECT TRIM(`mailbox`) AS mailbox, COUNT(DISTINCT `id`) AS email_count
FROM `enron_email`
WHERE `people` = 'allen-p'
  AND `mailbox` IS NOT NULL AND TRIM(`mailbox`) <> ''
GROUP BY TRIM(`mailbox`)
ORDER BY email_count DESC, mailbox ASC;

-- m10_phillip_reply_orig_senders
SELECT TRIM(o.`from`) AS original_sender,
       COUNT(DISTINCT i.`id`) AS email_count
FROM `enron_emailinfo` AS i
JOIN `enron_emailorig` AS o ON o.`id` = i.`id` AND o.`nth` = 1
WHERE LOWER(TRIM(i.`from`)) = 'phillip.allen@enron.com'
  AND LOWER(TRIM(i.`subject`)) LIKE 're:%'
  AND o.`from` IS NOT NULL AND TRIM(o.`from`) <> ''
GROUP BY TRIM(o.`from`)
ORDER BY email_count DESC, original_sender ASC
LIMIT 5;

-- m11_recipient_sequence_extremes
WITH to_seq AS (
  SELECT `id`, MAX(`nthto`) AS max_nthto
  FROM `enron_emailto`
  GROUP BY `id`
), xto_seq AS (
  SELECT `id`, MAX(`nthxto`) AS max_nthxto
  FROM `enron_emailxto`
  GROUP BY `id`
)
SELECT i.`id`, i.`subject`,
       COALESCE(t.max_nthto, 0) AS max_nthto,
       COALESCE(x.max_nthxto, 0) AS max_nthxto
FROM `enron_emailinfo` AS i
LEFT JOIN to_seq AS t ON t.`id` = i.`id`
LEFT JOIN xto_seq AS x ON x.`id` = i.`id`
ORDER BY GREATEST(COALESCE(t.max_nthto, 0), COALESCE(x.max_nthxto, 0)) DESC,
         i.`id` ASC
LIMIT 10;

-- m12_enron_announcements
SELECT LOWER(TRIM(t.`to`)) AS recipient,
       COUNT(DISTINCT t.`id`) AS email_count
FROM `enron_emailinfo` AS i
JOIN `enron_emailto` AS t ON t.`id` = i.`id`
WHERE LOWER(TRIM(i.`from`)) = 'enron.announcements@enron.com'
  AND t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
GROUP BY LOWER(TRIM(t.`to`))
ORDER BY email_count DESC, recipient ASC
LIMIT 5;

-- m13_source_file_stats
SELECT TRIM(`xfilename`) AS xfilename,
       COUNT(DISTINCT `id`) AS email_count
FROM `enron_source`
WHERE `xfilename` IS NOT NULL AND TRIM(`xfilename`) <> ''
GROUP BY TRIM(`xfilename`)
ORDER BY email_count DESC, xfilename ASC
LIMIT 5;

-- m14_recipient_representation_gap
WITH to_counts AS (
  SELECT `id`, COUNT(DISTINCT LOWER(TRIM(`to`))) AS to_count
  FROM `enron_emailto`
  WHERE `to` IS NOT NULL AND TRIM(`to`) <> ''
  GROUP BY `id`
), xto_counts AS (
  SELECT `id`, COUNT(DISTINCT TRIM(`xto`)) AS xto_count
  FROM `enron_emailxto`
  WHERE `xto` IS NOT NULL AND TRIM(`xto`) <> ''
  GROUP BY `id`
)
SELECT
  i.`id`,
  COALESCE(t.to_count, 0) AS to_count,
  COALESCE(x.xto_count, 0) AS xto_count,
  ABS(COALESCE(t.to_count, 0) - COALESCE(x.xto_count, 0)) AS absolute_gap,
  LEFT(i.`to`, 200) AS to_preview,
  LEFT(i.`xto`, 200) AS xto_preview
FROM `enron_emailinfo` AS i
LEFT JOIN to_counts AS t ON t.`id` = i.`id`
LEFT JOIN xto_counts AS x ON x.`id` = i.`id`
ORDER BY absolute_gap DESC, i.`id` ASC
LIMIT 10;

-- m15_sender_with_most_recipients
SELECT LOWER(TRIM(i.`from`)) AS sender,
       COUNT(DISTINCT LOWER(TRIM(t.`to`))) AS distinct_recipient_count
FROM `enron_emailinfo` AS i
JOIN `enron_emailto` AS t ON t.`id` = i.`id`
WHERE i.`from` IS NOT NULL AND TRIM(i.`from`) <> ''
  AND t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
GROUP BY LOWER(TRIM(i.`from`))
ORDER BY distinct_recipient_count DESC, sender ASC
LIMIT 1;

-- m16_deleted_items_owners
SELECT TRIM(`people`) AS people, COUNT(DISTINCT `id`) AS email_count
FROM `enron_email`
WHERE `mailbox` = 'deleted_items'
  AND `people` IS NOT NULL AND TRIM(`people`) <> ''
GROUP BY TRIM(`people`)
ORDER BY email_count DESC, people ASC;

-- m17_reply_orig_header_details
SELECT
  i.`id`,
  i.`subject` AS current_subject,
  o.`subject` AS original_subject,
  o.`from` AS original_from,
  o.`to` AS original_to,
  o.`xfrom` AS original_xfrom,
  o.`xto` AS original_xto
FROM `enron_emailinfo` AS i
JOIN `enron_emailorig` AS o ON o.`id` = i.`id` AND o.`nth` = 1
WHERE LOWER(TRIM(i.`subject`)) LIKE 're:%'
ORDER BY i.`id` ASC;

-- m18_october_2001_recipients
WITH parsed AS (
  SELECT
    `id`,
    STR_TO_DATE(
      REGEXP_SUBSTR(`date`, '^[A-Za-z]{3}, [0-9]{1,2} [A-Za-z]{3} [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}'),
      '%a, %e %b %Y %H:%i:%s'
    ) AS parsed_datetime
  FROM `enron_emailinfo`
)
SELECT LOWER(TRIM(t.`to`)) AS recipient,
       COUNT(DISTINCT t.`id`) AS email_count
FROM parsed AS p
JOIN `enron_emailto` AS t ON t.`id` = p.`id`
WHERE YEAR(p.parsed_datetime) = 2001
  AND MONTH(p.parsed_datetime) = 10
  AND t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
GROUP BY LOWER(TRIM(t.`to`))
ORDER BY email_count DESC, recipient ASC
LIMIT 5;

-- m19_larry_inbox_count
SELECT COUNT(DISTINCT i.`id`) AS email_count
FROM `enron_emailinfo` AS i
JOIN `enron_email` AS e ON e.`id` = i.`id`
WHERE LOWER(TRIM(i.`from`)) = 'larry.campbell@enron.com'
  AND e.`mailbox` = 'inbox';

-- m20_top_source_origins
SELECT TRIM(`xorigin`) AS xorigin, COUNT(DISTINCT `id`) AS email_count
FROM `enron_source`
WHERE `xorigin` IS NOT NULL AND TRIM(`xorigin`) <> ''
GROUP BY TRIM(`xorigin`)
ORDER BY email_count DESC, xorigin ASC
LIMIT 5;

-- h01_two_way_communication
WITH senders AS (
  SELECT DISTINCT LOWER(TRIM(`from`)) AS address
  FROM `enron_emailinfo`
  WHERE `from` IS NOT NULL AND TRIM(`from`) <> ''
), recipients AS (
  SELECT DISTINCT LOWER(TRIM(`to`)) AS address
  FROM `enron_emailto`
  WHERE `to` IS NOT NULL AND TRIM(`to`) <> ''
)
SELECT COUNT(*) AS two_way_address_count
FROM senders AS s
JOIN recipients AS r ON r.address = s.address;

-- h02_sender_no_receiver
WITH sender_counts AS (
  SELECT LOWER(TRIM(`from`)) AS address,
         COUNT(DISTINCT `id`) AS sent_email_count
  FROM `enron_emailinfo`
  WHERE `from` IS NOT NULL AND TRIM(`from`) <> ''
  GROUP BY LOWER(TRIM(`from`))
), recipients AS (
  SELECT DISTINCT LOWER(TRIM(`to`)) AS address
  FROM `enron_emailto`
  WHERE `to` IS NOT NULL AND TRIM(`to`) <> ''
)
SELECT s.address, s.sent_email_count
FROM sender_counts AS s
LEFT JOIN recipients AS r ON r.address = s.address
WHERE r.address IS NULL
ORDER BY s.sent_email_count DESC, s.address ASC;

-- h03_most_active_email_thread
WITH replies AS (
  SELECT
    `id`,
    LOWER(TRIM(REGEXP_REPLACE(
      TRIM(`subject`),
      '^(re:[[:space:]]*)+',
      '', 1, 0, 'i'
    ))) AS normalized_subject
  FROM `enron_emailinfo`
  WHERE LOWER(TRIM(`subject`)) LIKE 're:%'
)
SELECT normalized_subject, COUNT(DISTINCT `id`) AS reply_email_count
FROM replies
WHERE normalized_subject <> ''
GROUP BY normalized_subject
ORDER BY reply_email_count DESC, normalized_subject ASC
LIMIT 3;

-- h04_top_senders_per_owner
WITH sender_counts AS (
  SELECT
    TRIM(e.`people`) AS people,
    LOWER(TRIM(i.`from`)) AS sender,
    COUNT(DISTINCT i.`id`) AS email_count
  FROM `enron_email` AS e
  JOIN `enron_emailinfo` AS i ON i.`id` = e.`id`
  WHERE e.`people` IS NOT NULL AND TRIM(e.`people`) <> ''
    AND i.`from` IS NOT NULL AND TRIM(i.`from`) <> ''
  GROUP BY TRIM(e.`people`), LOWER(TRIM(i.`from`))
), ranked AS (
  SELECT
    people, sender, email_count,
    ROW_NUMBER() OVER (
      PARTITION BY people
      ORDER BY email_count DESC, sender ASC
    ) AS sender_rank
  FROM sender_counts
)
SELECT people, sender, email_count, sender_rank
FROM ranked
WHERE sender_rank <= 3
ORDER BY people ASC, sender_rank ASC;

-- h05_busiest_day_senders
WITH parsed AS (
  SELECT
    `id`,
    LOWER(TRIM(`from`)) AS sender,
    DATE(STR_TO_DATE(
      REGEXP_SUBSTR(`date`, '^[A-Za-z]{3}, [0-9]{1,2} [A-Za-z]{3} [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}'),
      '%a, %e %b %Y %H:%i:%s'
    )) AS sent_date
  FROM `enron_emailinfo`
), day_counts AS (
  SELECT sent_date, COUNT(DISTINCT `id`) AS email_count
  FROM parsed
  WHERE sent_date IS NOT NULL
  GROUP BY sent_date
), busiest_day AS (
  SELECT sent_date
  FROM day_counts
  ORDER BY email_count DESC, sent_date ASC
  LIMIT 1
), sender_counts AS (
  SELECT p.sent_date, p.sender, COUNT(DISTINCT p.`id`) AS email_count
  FROM parsed AS p
  JOIN busiest_day AS b ON b.sent_date = p.sent_date
  WHERE p.sender IS NOT NULL AND p.sender <> ''
  GROUP BY p.sent_date, p.sender
)
SELECT sent_date, sender, email_count
FROM sender_counts
ORDER BY email_count DESC, sender ASC
LIMIT 5;

-- h06_internal_vs_external
WITH classified AS (
  SELECT
    `id`,
    CASE
      WHEN LOWER(TRIM(`from`)) LIKE '%@enron.com' THEN 'internal'
      ELSE 'external'
    END AS sender_type
  FROM `enron_emailinfo`
  WHERE `from` IS NOT NULL AND TRIM(`from`) <> ''
), counts AS (
  SELECT sender_type, COUNT(DISTINCT `id`) AS email_count
  FROM classified
  GROUP BY sender_type
), total AS (
  SELECT COUNT(DISTINCT `id`) AS total_count
  FROM classified
)
SELECT c.sender_type, c.email_count,
       ROUND(100.0 * c.email_count / NULLIF(t.total_count, 0), 2) AS percentage
FROM counts AS c
CROSS JOIN total AS t
ORDER BY c.sender_type ASC;

-- h07_sender_receiver_overlap_people
WITH communication_addresses AS (
  SELECT DISTINCT TRIM(e.`people`) AS people,
                  LOWER(TRIM(i.`from`)) AS address
  FROM `enron_email` AS e
  JOIN `enron_emailinfo` AS i ON i.`id` = e.`id`
  WHERE e.`people` IN ('campbell-l', 'allen-p', 'badeer-r')
    AND i.`from` IS NOT NULL AND TRIM(i.`from`) <> ''

  UNION

  SELECT DISTINCT TRIM(e.`people`) AS people,
                  LOWER(TRIM(t.`to`)) AS address
  FROM `enron_email` AS e
  JOIN `enron_emailto` AS t ON t.`id` = e.`id`
  WHERE e.`people` IN ('campbell-l', 'allen-p', 'badeer-r')
    AND t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
)
SELECT address, COUNT(DISTINCT people) AS people_count
FROM communication_addresses
GROUP BY address
HAVING COUNT(DISTINCT people) >= 2
ORDER BY people_count DESC, address ASC;

-- h08_campbell_allen_shared_recipients
WITH recipient_counts AS (
  SELECT
    LOWER(TRIM(t.`to`)) AS recipient,
    COUNT(DISTINCT CASE
      WHEN LOWER(TRIM(i.`from`)) = 'larry.campbell@enron.com' THEN i.`id`
    END) AS larry_email_count,
    COUNT(DISTINCT CASE
      WHEN LOWER(TRIM(i.`from`)) = 'phillip.allen@enron.com' THEN i.`id`
    END) AS phillip_email_count
  FROM `enron_emailinfo` AS i
  JOIN `enron_emailto` AS t ON t.`id` = i.`id`
  WHERE LOWER(TRIM(i.`from`)) IN (
    'larry.campbell@enron.com',
    'phillip.allen@enron.com'
  )
    AND t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
  GROUP BY LOWER(TRIM(t.`to`))
)
SELECT recipient, larry_email_count, phillip_email_count
FROM recipient_counts
WHERE larry_email_count > 0 AND phillip_email_count > 0
ORDER BY (larry_email_count + phillip_email_count) DESC, recipient ASC;

-- h09_email_chain_depth
WITH per_email AS (
  SELECT `id`, COUNT(*) AS historical_header_count
  FROM `enron_emailorig`
  GROUP BY `id`
)
SELECT
  ROUND(AVG(historical_header_count), 4) AS avg_historical_header_count,
  MAX(historical_header_count) AS max_historical_header_count,
  SUM(CASE WHEN historical_header_count >= 3 THEN 1 ELSE 0 END) AS emails_with_at_least_3
FROM per_email;

-- h10_top_folder_per_person
WITH folder_counts AS (
  SELECT
    TRIM(`people`) AS people,
    TRIM(`mailbox`) AS mailbox,
    COUNT(DISTINCT `id`) AS email_count
  FROM `enron_email`
  WHERE `people` IS NOT NULL AND TRIM(`people`) <> ''
    AND `mailbox` IS NOT NULL AND TRIM(`mailbox`) <> ''
  GROUP BY TRIM(`people`), TRIM(`mailbox`)
), ranked AS (
  SELECT
    people, mailbox, email_count,
    DENSE_RANK() OVER (
      PARTITION BY people
      ORDER BY email_count DESC
    ) AS folder_rank
  FROM folder_counts
)
SELECT people, mailbox, email_count
FROM ranked
WHERE folder_rank = 1
ORDER BY people ASC, mailbox ASC;
