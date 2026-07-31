## Analysis

距离计算方法主要有：

(1) 欧氏距离'euclidean'c =  $ \sqrt{(x_1 - x_2)^2 + (y_1 - y_2)^2} $

(2) 曼哈顿距离'manhattan':  $ c = |x_1 - x_2| + |y_1 - y_2| $

(3) 切比雪夫距离'chebyshev's Dayshev (p, q) :=  $ \max_{i}(|p_i - q_i|) $

(4) 闵可夫斯基距离'minkowski  $ d_{12} = \sqrt[p]{\sum_{k=1}^{n} |x_{1k} - x_{2k}|^p} $

(5) 带权重闵可夫斯基距离'wminkowsk $ d_{12}=\sqrt{\sum_{k=1}^{n}(x_{1k}-x_{2k})^{2}} $，其中w为特征权重

（6）标准化欧氏距离'seuclidean'：即对于各特征维度做了归一化以后的欧氏距离。此时个样本特征维度的均值为0，方差为1.

(7) 马氏距离‘mahalanobis’:  $ D_M(x) = \sqrt{(x - \mu)^T \Sigma^{-1}(x - \mu)} $ 中，为样本协方差矩阵的逆矩阵。当样本分布独立时，S为单位矩阵，此时马氏距离等同于欧氏距离。