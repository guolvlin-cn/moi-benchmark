
<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>DocNo.:xx-xxxx-xx-xxxx</td><td style='text-align: center; word-wrap: break-word;'>Doc.Title:SMIC200mmxxxxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx</td><td style='text-align: center; word-wrap: break-word;'>Rec.:1</td><td style='text-align: center; word-wrap: break-word;'>Page No.:1/3</td></tr></table>

1. Project background and objectives

1.1. DCC: Document Control Center

1.2. DCN: Document Change Notice(for Company Rules and Regulations)

1.3. DMS: Document Management System

#### 1.4. Background description

With the continuous evolution of artificial intelligence technology, large language models (LLM) and multimodal models have demonstrated remarkable capabilities in comprehension, generation, and reasoning. An increasing number of enterprises are beginning to experiment with integrating AI technology into their actual business processes, aiming to enhance information processing efficiency, optimize decision-making quality, and reduce reliance on human experience. Against this backdrop.

##### 1.4.1. Industry prospects

A. The current industry as a whole exhibits the following characteristics:

B. The capabilities of pre-trained models have rapidly improved, but there are still differences in scenario generalization

C. The scale of internal data within the enterprise continues to grow, leading to a strong demand for intelligent retrieval and analysis

D. AI systems are gradually evolving from single-point applications towards platformization and servitization

E. Main pain points

F. In the actual implementation process, common issues include but are not limited to:

G. The data sources are complex, with a coexistence of structured, semi-structured, and unstructured data

H. The coupling between model services and business logic is too high, resulting in poor system maintainability

I. Without a unified evaluation and monitoring mechanism, it is difficult to continuously ensure the effectiveness of the model.

a. 为了能使 Reticle Stocker 钠够正确快速的读取光照条码，光照 MA 必须使用 Barcode Reader 扫描自光照厂所送出的 Barcode（以有效防止人为之输入错误），之后再利用光照室旁的 Barcode Printer 打印 Reticle ID，并贴雨 Reticle POD 之上。

b. Barcode 使用 9cm X 3cm 标签打印，它的形式如下（图四）：

<div style="text-align: center;"><img src="https://xmind-parser.bj.bcebos.com/vlm_cloud/parseResult/task-yOEn6beKt4Z2xyExFmG59w8JoxKpgLwD/0-21.jpg?authorization=bce-auth-v1%2FALTAK7IDj758EUbA1igu04rHAh%2F2026-07-27T04%3A45%3A10Z%2F2592000%2F%2F1cd618f313f6822c0a3df5bd9e9c4d224c70b685f8cf51b69d2620bf18f2c94d" alt="Image" width="38%" /></div>


001800 111AA. IDA

图四 Barcode 打印实例


<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>DocNo.:xx-xxxx-xx-xxxx</td><td style='text-align: center; word-wrap: break-word;'>Doc.Title:SMIC200mmxxxxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx</td><td style='text-align: center; word-wrap: break-word;'>Rec.:1</td><td style='text-align: center; word-wrap: break-word;'>Page No.:2/3</td></tr></table>

c. Recicle POD Size:  $ 227.33W \times 230L \times 92.2H $ (mm). Barcode 打印完毕后，要贴在 Reticle POD 的适当位置上，才能被 Reticle Stock 顺利地读出。Barcode 贴在 POD 上的位置如下（图五）所示：

<div style="text-align: center;"><img src="https://xmind-parser.bj.bcebos.com/vlm_cloud/parseResult/task-yOEn6beKt4Z2xyExFmG59w8JoxKpgLwD/1-4.jpg?authorization=bce-auth-v1%2FALTAK7IDj758EUbA1igu04rHAh%2F2026-07-27T04%3A45%3A10Z%2F2592000%2F%2Ff6201b98bf741dcdd289ce3554d6fbd1850980e40150289fd04be8596f16ed9c" alt="Image" width="75%" /></div>


<div style="text-align: center;">图五 Barcode 位置及贴法</div>


#### 1.5. 技术选型说明

##### 1.5.1. 后端与基础设施

编程语言：Python

服务框架：FastAPI

模型部署：vLLM / Triton

容器与编排：Docker + Kubernetes

##### 1.5.2. 模型相关

大语言模型 (LLM)

向量模型（Embedding）

• RAG 检索增强生成

##### 1.5.3. 其他模型相关

视觉大模型 (VLM)

向量模型（Embedding）

• RAG 检索增强生成

1.6. Technical selection description

1.6.1. Backend and Infrastructure

• Programming language: Python

• Service framework: FastAPI

The information contained herein is exclusive property of SIMC, and shall not be distributed, reproduced, or disclosed in whole or in part without prior written permission of SMIC

<div style="text-align: center;">Semiconfuctor Manufactcuturing International Corporation</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>DocNo.:xx-xxxx-xx-xxxx</td><td style='text-align: center; word-wrap: break-word;'>Doc.Title:SMIC200mmxxxxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx</td><td style='text-align: center; word-wrap: break-word;'>Rec.:1</td><td style='text-align: center; word-wrap: break-word;'>Page No.:3/3</td></tr></table>

• Model deployment: vLLM / Triton

• Containers and orchestration: Docker + Kubernetes

1.6.2. Model-related

- Large Language Model (LLM)

• Vector model (Embedding)

RAG: Retrieval Augmented Generation

1.6.3. Other model-related

- Visual Large Model (VLM)

• Vector model (Embedding)