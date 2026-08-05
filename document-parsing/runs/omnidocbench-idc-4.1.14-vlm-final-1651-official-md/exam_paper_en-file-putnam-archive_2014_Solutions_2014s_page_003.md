  Corollary 2 to $(P_{j}(x) - P_{i}(x)) / x^{i - 1}$ , we see that $|z|\geq 1 - \frac{1}{i + 2}$ , contradiction.
  Remark: Elkies also reports that this problem is his submission, dating back to 2005 and arising from work of Joe Harris. It dates back further to Example 3.7 in: Hajime Kaji, On the tangentially degenerate curves, J. London Math. Soc. (2) 33 (1986), 430-440, in which the second solution is given.

  Remark: Elkies points out a mild generalization which may be treated using the first solution but not the second: for integers $a < b < c < d$ and $z \in \mathbb{C}$ which is neither zero nor a root of unity, the matrix
              $$\left( \begin{array}{\text{ccc} c} 1 & 1 & 1 & 1 \\ a & b & c & d \\ z ^ {a} & z ^ {b} & z ^ {c} & z ^ {d} \end{array} \right)$$
  has rank 3 (the problem at hand being the case a = 0, b = 1, c = i + 1, d = j + 1 ).

  Remark: It seems likely that the individual polynomials $P_{k}(x)$ are all irreducible, but this appears difficult to prove.

  Third solution: (by David Feldman) Note that

        $$P _ {n} (x) (1 - x) = 1 + x + \dots + x ^ {n - 1} - n x ^ {n}.$$
  If $|z| \geq 1$, then
      $$n | z | ^ {n} \geq | z | ^ {n - 1} + \dots + 1 \geq | z ^ {n - 1} + \dots + 1 |,$$
  with the first equality occurring only if $|z| = 1$ and the second equality occurring only if $z$ is a positive real number. Hence the equation $P_{n}(z)(1 - z) = 0$ has no solutions with $|z| \geq 1$ other than the trivial solution $z = 1$. Since
        $$P _ {n} (x) (1 - x) ^ {2} = 1 - (n + 1) x ^ {n} + n x ^ {n + 1},$$
  it now suffices to check that the curves

    $$C _ {n} = \left\{z \in \mathbb{C}: 0 <   | z | <   1, | z | ^ {n} | n + 1 - z n | = 1 \right\}$$
  are pairwise disjoint as n varies over positive integers.

  Write $z = u + iv$; we may assume without loss of generality that $v \geq 0$. Define the function
          $$E _ {z} (n) = n \log | z | + \log | n + 1 - z n |.$$
  One computes that for $n \in \mathbb{R}$ , $E_z^{\prime \prime}(n) < 0$ if and only if
            $$\frac{u - v - 1}{(1 - u) ^ {2} + v ^ {2}} <   n <   \frac{u + v - 1}{(1 - u) ^ {2} + v ^ {2}}.$$
  In addition, $E_{z}(0) = 0$ and
$$E _ {z} ^ {\prime} (0) = \frac{1}{2} \log \left(u ^ {2} + v ^ {2}\right) + (1 - u) \geq \log (u) + 1 - u \geq 0$$
  since $\log(u)$ is concave. From this, it follows that the equation $E_z(n) = 0$ can have at most one solution with $n > 0$.
  Remark: The reader may notice a strong similarity between this solution and the first solution. The primary difference is we compute that $E_z'(0) \geq 0$ instead of discovering that $E_z(-1) = 0$.
  Remark: It is also possible to solve this problem using a p -adic valuation on the field of algebraic numbers in place of the complex absolute value; however, this leads to a substantially more complicated solution. In lieu of including such a solution here, we refer to the approach described by Victor Wang here: http://www.artofproblemsolving.com/Forum/viewtopic.php?f=80&t=616731.

## A6 The largest such $k$ is $n^n$. We first show that this value can be achieved by an explicit construction. Let $e_1, \ldots, e_n$ be the standard basis of $\mathbb{R}^n$. For $i_1, \ldots, i_n \in \{1, \ldots, n\}$, let $M_{i_1, \ldots, i_n}$ be the matrix with row vectors $e_{i_1}, \ldots, e_{i_n}$, and let $N_{i_1, \ldots, i_n}$ be the transpose of $M_{i_1, \ldots, i_n}$. Then $M_{i_1, \ldots, i_n} N_{j_1, \ldots, j_n}$ has $k$-th diagonal entry $e_{i_k} \cdot e_{j_k}$, proving the claim.

  We next show that for any families of matrices $M_{i}, N_{j}$ as described, we must have $k \leq n^{n}$. Let $V$ be the $n$-fold tensor product of $\mathbb{R}^n$, i.e., the vector space with orthonormal basis $e_{i_1} \otimes \dots \otimes e_{i_n}$ for $i_1, \ldots , i_n \in \{1, \ldots , n\}$. Let $m_{i}$ be the tensor product of the rows of $M_{i}$; that is,
    $$m _ {i} = \sum_ {i _ {1}, \dots , i _ {n} = 1} ^ {n} (M _ {i}) _ {1, i _ {1}} \dots (M _ {i}) _ {n, i _ {n}} e _ {i _ {1}} \otimes \dots \otimes e _ {i _ {n}}.$$
  Similarly, let $n_j$ be the tensor product of the columns of $N_j$. One computes easily that $m_i \cdot n_j$ equals the product of the diagonal entries of $M_i N_j$, and so vanishes if and only if $i \neq j$. For any $c_i \in \mathbb{R}$ such that $\sum_{i} c_i m_i = 0$, for each $j$ we have
      $$0 = \left(\sum_ {i} c _ {i} m _ {i}\right) \cdot n _ {j} = \sum_ {i} c _ {i} \left(m _ {i} \cdot n _ {j}\right) = c _ {j}.$$
  Therefore the vectors $m_{1},\ldots ,m_{k}$ in $V$ are linearly independent, implying $k\leq n^n$ as desired.

  Remark: Noam Elkies points out that similar arguments may be made in the case that the $M_{i}$ are $m\times n$ matrices and the $N_{j}$ are $n\times m$ matrices.

## B1 These are the integers with no 0's in their usual base 10 expansion. If the usual base 10 expansion of $N$ is $d_k 10^k + \dots + d_0 10^0$ and one of the digits is 0, then there exists an $i \leq k - 1$ such that $d_i = 0$ and $d_{i+1} > 0$; then we can replace $d_{i+1} 10^{i+1} + (0) 10^i$ by $(d_{i+1} - 1) 10^{i+1} + (10) 10^i$ to obtain a second base 10 over-expansion.

  We claim conversely that if $N$ has no 0's in its usual base 10 expansion, then this standard form is the unique base 10 over-expansion for $N$. This holds by induction on the number of digits of $N$: if $1 \leq N \leq 9$, then the result is clear. Otherwise, any base 10 over-expansion $N = d_k 10^k + \dots + d_1 10 + d_0 10^0$ must have $d_0 \equiv N \pmod{10}$, which uniquely determines $d_0$ since
