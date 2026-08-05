as desired.

Remark: The use of Cesaro's lemma above is the special case $b_{n} = n$ of the Cesaro-Stolz theorem: if $a_{n}, b_{n}$ are sequences such that $b_{n}$ is positive, strictly increasing, and unbounded, and
  $$\lim  _ {n \rightarrow \infty} \frac{a _ {n + 1} - a _ {n}}{b _ {n + 1} - b _ {n}} = L,$$
then

    $$\lim  _ {n \rightarrow \infty} \frac{a _ {n}}{b _ {n}} = L.$$
Second solution: In this solution, rather than applying Taylor's theorem with remainder to $(1 + x)^m$ for $1 < m < 2$ and $x > 0$, we only apply convexity to deduce that $(1 + x)^m \geq 1 + mx$. This gives
  $$a _ {n + 1} ^ {(k + 1) / k} - a _ {n} ^ {(k + 1) / k} \geq \frac{k + 1}{k},$$
and so

  $$a _ {n} ^ {(k + 1) / k} \geq \frac{k + 1}{k} n + c$$
for some $c \in \mathbb{R}$. In particular,
    $$\lim  _ {n \rightarrow \infty} \inf  _ {n \rightarrow \infty} \frac{a _ {n} ^ {(k + 1) / k}}{n} \geq \frac{k + 1}{k}$$
and so

      $$\lim  _ {n \rightarrow \infty} \inf  _ {n ^ {k / (k + 1)}} \frac{a _ {n}}{n ^ {k / (k + 1)}} \geq \left(\frac{k + 1}{k}\right) ^ {k / (k + 1)}.$$
But turning this around, the fact that

  $$\begin{array}{l} a _ {n + 1} - a _ {n} \\ = a _ {n} ^ {- 1 / k} \\ \leq \left(\frac{k + 1}{k}\right) ^ {- 1 / (k + 1)} n ^ {- 1 / (k + 1)} (1 + o (1)), \\ \end{array}$$
where $o(1)$ denotes a function tending to 0 as $n \to \infty$, yields
    $$\begin{array}{l} a _ {n} \\ \leq \left(\frac{k + 1}{k}\right) ^ {- 1 / (k + 1)} \sum_ {i = 1} ^ {n} i ^ {- 1 / (k + 1)} (1 + o (1)) \\ = \frac{k + 1}{k} \left(\frac{k + 1}{k}\right) ^ {- 1 / (k + 1)} n ^ {k / (k + 1)} (1 + o (1)) \\ = \left(\frac{k + 1}{k}\right) ^ {k / (k + 1)} n ^ {k / (k + 1)} (1 + o (1)), \\ \end{array}$$
so

$$\lim  _ {n \rightarrow \infty} \sup  _ {n \rightarrow \infty} \frac{a _ {n}}{n ^ {k / (k + 1)}} \leq \left(\frac{k + 1}{k}\right) ^ {k / (k + 1)}$$
and this completes the proof.

Third solution: We argue that $a_{n}\to \infty$ as in the first solution. Write $b_{n} = a_{n} - Ln^{k / (k + 1)}$, for a value of $L$ to be determined later. We have
  $$\begin{array}{l} b _ {n + 1} \\ = b _ {n} + a _ {n} ^ {- 1 / k} - L \left(\left(n + 1\right) ^ {k / (k + 1)} - n ^ {k / (k + 1)}\right) \\ = e _ {1} + e _ {2}, \\ \end{array}$$
where

  $$\begin{array}{l} e _ {1} = b _ {n} + a _ {n} ^ {- 1 / k} - L ^ {- 1 / k} n ^ {- 1 / (k + 1)} \\ e _ {2} = L \left(\left(n + 1\right) ^ {k / (k + 1)} - n ^ {k / (k + 1)}\right) \\ - L ^ {- 1 / k} n ^ {- 1 / (k + 1)}. \\ \end{array}$$
We first estimate $e_1$. For $-1 < m < 0$, by the convexity of $(1 + x)^m$ and $(1 + x)^{1 - m}$, we have
    $$\begin{array}{l} 1 + m x \leq (1 + x) ^ {m} \\ \leq 1 + m x (1 + x) ^ {m - 1}. \\ \end{array}$$
Hence

  $$\begin{array}{l} - \frac{1}{k} L ^ {- (k + 1) / k} n ^ {- 1} b _ {n} \leq e _ {1} - b _ {n} \\ \leq - \frac{1}{k} b _ {n} a _ {n} ^ {- (k + 1) / k}. \\ \end{array}$$
Note that both bounds have sign opposite to $b_{n}$; moreover, by the bound $a_{n} = \Omega(n^{(k - 1) / k})$, both bounds have absolutely value strictly less than that of $b_{n}$ for $n$ sufficiently large. Consequently, for $n$ large,
          $$\left| e _ {1} \right| \leq \left| b _ {n} \right|.$$
We now work on $e_2$. By Taylor's theorem with remainder applied to $(1 + x)^m$ for $x > 0$ and $0 < m < 1$,
    $$\begin{array}{l} 1 + m x \geq (1 + x) ^ {m} \\ \geq 1 + m x + \frac{m (m - 1)}{2} x ^ {2}. \\ \end{array}$$
The "main term" of $L((n + 1)^{k / (k + 1)} - n^{k / (k + 1)})$ is $L_{\frac{k}{k + 1}}n^{-1 / (k + 1)}$. To make this coincide with $L^{-1 / k}n^{-1 / (k + 1)}$, we take
          $$L = \left(\frac{k + 1}{k}\right) ^ {k / (k + 1)}.$$
We then find that

        $$\left| e _ {2} \right| = O \left(n ^ {- 2}\right),$$
and because $b_{n+1} = e_1 + e_2$, we have $|b_{n+1}| \leq |b_n| + |e_2|$. Hence
      $$| b _ {n} | = O \left(\sum_ {i = 1} ^ {n} i ^ {- 2}\right) = O (1),$$
