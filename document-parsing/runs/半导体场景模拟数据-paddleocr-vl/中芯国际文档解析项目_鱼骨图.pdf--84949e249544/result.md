# 中芯国际文档解析项目 开工会

2025年12月26日

## 会议议程

01 项目背景    
02 需求分析    
03 项目计划    
04 项目协作    
05 风险应对

## 项目背景介绍

## 中芯国际 SMIC 文档解析开发项目

主要是为了对PDF、PPT、Word、Excel等多种格式文件以及图片、表格、流程图等内容进行解析，将非结构化数据转化为结构化数据并利用。

基于大模型算法构建文档要素抽取引擎，实现对PDF、PPT、Word、Excel等文档以及文档内图片、表格、流程图等复杂数据的解析分析，最终形成可支持智能问答系统、AI数字员工、光刻机异常分析助手、PDE培训数字员工、QE/CE稽核数字员工等应用的功能模块。

<div style="text-align: center;"><img src="https://xmind-parser.bj.bcebos.com/vlm_cloud/parseResult/task-SawfOL9LY1JFVouHjmX9094Zir2IyXdL/2-4.jpg?authorization=bce-auth-v1%2FALTAK7IDj758EUbA1igu04rHAh%2F2026-07-27T04%3A49%3A55Z%2F2592000%2F%2Fa30b90418ec7a73892e16414f3ecf0a6814624bceffd4e4d6ba081fbd3616321" alt="Image" width="66%" /></div>


智能问答系统  
AI 数字员工  
PDE 培训数字员工  
QE/CE稽核数字员工

## 产品需求分析

<div style="text-align: center;">需求示例1如下图</div>


<div style="text-align: center;"><img src="https://xmind-parser.bj.bcebos.com/vlm_cloud/parseResult/task-SawfOL9LY1JFVouHjmX9094Zir2IyXdL/3-3.jpg?authorization=bce-auth-v1%2FALTAK7IDj758EUbA1igu04rHAh%2F2026-07-27T04%3A49%3A55Z%2F2592000%2F%2F98cf64e62f8aaa1e340004c9119862cacfe89d97131201c3d6fb5a302325d1e4" alt="Image" width="32%" /></div>


<div style="text-align: center;">需求示例1如下图</div>


<div style="text-align: center;"><img src="https://xmind-parser.bj.bcebos.com/vlm_cloud/parseResult/task-SawfOL9LY1JFVouHjmX9094Zir2IyXdL/3-5.jpg?authorization=bce-auth-v1%2FALTAK7IDj758EUbA1igu04rHAh%2F2026-07-27T04%3A49%3A55Z%2F2592000%2F%2Fb7a865cd3a03bbe2344fe17bf78ccce183cf4a54eaf226656a6eef90cc8ba082" alt="Image" width="25%" /></div>


## 产品需求分析鱼骨图

## 文字公式解析

标题层级关系

块级和行级公式

中英文混合

## 高可用

宕机自动回复

多节点部署

文档优先解析策略

多种文件统一接口

## 接口对接

API可调试

API可配置

多场景流程图识别解析

跨页表和多线表解析

表格和图片混合解析

图片理解表格解析

资源可监控

计算资源扩展

可扩展/高并发

## 产品需求分析计划

最终交付目标为 100%，时间 2025/1/19


<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>需求类别</td><td style='text-align: center; word-wrap: break-word;'>子类别</td><td style='text-align: center; word-wrap: break-word;'>需求概要</td><td style='text-align: center; word-wrap: break-word;'>MOI 满足情况</td><td style='text-align: center; word-wrap: break-word;'>MOI 满足度</td></tr><tr><td rowspan="4">解析</td><td style='text-align: center; word-wrap: break-word;'>文字解析</td><td style='text-align: center; word-wrap: break-word;'>能够正确识别全字符集，对文档中的标题、正文及其层级内容可以正确区别，识别中日英等混合语言的文档。</td><td style='text-align: center; word-wrap: break-word;'>不支持页眉页脚解析</td><td style='text-align: center; word-wrap: break-word;'>95%</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>图片理解</td><td style='text-align: center; word-wrap: break-word;'>对流程图、图表、图文混合图像等图片类型进行正确的文字提取和语义理解，提供必要的跨页合并和结构化数据输出，支持多中图片文件类型的解析。</td><td style='text-align: center; word-wrap: break-word;'>Caption 理解效果需要提升\n不支持图表解析为结构化数据</td><td style='text-align: center; word-wrap: break-word;'>70%</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>表格解析</td><td style='text-align: center; word-wrap: break-word;'>能够正确按照表格拓普输出结构化数据，对表格中的嵌入图片正确理解，支持跨页表格以及 excel 中的离散表格识别提取</td><td style='text-align: center; word-wrap: break-word;'>不支持跨页表格拼接\n不支持是否合并单元格输出控制</td><td style='text-align: center; word-wrap: break-word;'>80%</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>公式解析</td><td style='text-align: center; word-wrap: break-word;'>正确识别 Office 文档中各个位置的公式，并输出为 markdown 公式语法</td><td style='text-align: center; word-wrap: break-word;'>行级、表格内公式无法识别</td><td style='text-align: center; word-wrap: break-word;'>70%</td></tr><tr><td rowspan="2">性能</td><td style='text-align: center; word-wrap: break-word;'>可扩展 / 高并发</td><td style='text-align: center; word-wrap: break-word;'>支持计算资源的横向扩展，支持 500 人高并发访问</td><td style='text-align: center; word-wrap: break-word;'>支持计算资源扩展，支持任务并发配置及文件内图片解析并发</td><td style='text-align: center; word-wrap: break-word;'>100%</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>高可用</td><td style='text-align: center; word-wrap: break-word;'>支持系统宕机自动恢复，高负载持续运行，并在多节点部署，支持文档优先解析策略。</td><td style='text-align: center; word-wrap: break-word;'>计算节点为无状态服务节点</td><td style='text-align: center; word-wrap: break-word;'>100%</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>可视化</td><td style='text-align: center; word-wrap: break-word;'>可观测</td><td style='text-align: center; word-wrap: break-word;'>对系统的监控状态检测，提供任务监控及审计日志，具有自动清理数据的能力。</td><td style='text-align: center; word-wrap: break-word;'>基础的信息都有记录，待信息整合\n不支持 API 调用后自动清理数据</td><td style='text-align: center; word-wrap: break-word;'>70%</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>API</td><td style='text-align: center; word-wrap: break-word;'>接口对接</td><td style='text-align: center; word-wrap: break-word;'>支持单一 API 对各种类型文档解析，API 可配置是否返回原始文件、数据清除、批量解析、状态推送等</td><td style='text-align: center; word-wrap: break-word;'>已支持基础的 API 接口，待支持若干可配置功能</td><td style='text-align: center; word-wrap: break-word;'>80%</td></tr></table>