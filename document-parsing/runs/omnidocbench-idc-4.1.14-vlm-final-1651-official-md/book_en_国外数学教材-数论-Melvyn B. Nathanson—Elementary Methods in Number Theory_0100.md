Proof. This follows immediately from Theorem 3.3, since $|(\mathbf{Z} / p\mathbf{Z})^{\times}| = p - 1$. \square
The following table lists the primitive roots for the first six primes.

<table><tr><td>p</td><td>φ(p−1)</td><td>primitive roots</td></tr><tr><td>2</td><td>1</td><td>1</td></tr><tr><td>3</td><td>1</td><td>2</td></tr><tr><td>5</td><td>2</td><td>2,3</td></tr><tr><td>7</td><td>2</td><td>3,5</td></tr><tr><td>11</td><td>4</td><td>2,6,7,8</td></tr><tr><td>13</td><td>4</td><td>2,6,7,11</td></tr></table>

Let p be a prime, and let g be a primitive root modulo p . If a is an integer not divisible by p , then there exists a unique integer k such that

  $$a \equiv g ^ {k} \pmod{p}$$
and

    $$k \in \{0, 1, \dots , p - 2 \}.$$
This integer k is called the index of a with respect to the primitive root g , and is denoted by

      $$k = \operatorname{i n d} _ {g} (a).$$
If $k_{1}$ and $k_{2}$ are any integers such that $k_{1} \leq k_{2}$ and
  $$a \equiv g ^ {k _ {1}} \equiv g ^ {k _ {2}} \pmod{p},$$
then

$$g ^ {k _ {2} - k _ {1}} \equiv 1 \pmod{p},$$
and so

      $$k _ {1} \equiv k _ {2} \pmod{p - 1}.$$
If $a \equiv g^k \pmod{p}$ and $b \equiv g^{\ell} \pmod{p}$, then $ab \equiv g^k g^{\ell} = g^{k+\ell} \pmod{p}$, and so
    $$\operatorname{i n d} _ {g} (a b) \equiv k + \ell \equiv \operatorname{i n d} _ {g} (a) + \operatorname{i n d} _ {g} (b) \pmod{p - 1}.$$
The index map $\operatorname{ind}_g$ is also called the discrete logarithm to the base $g$ modulo $p$.
  For example, $2$ is a primitive root modulo $13$. Here is a table of $\operatorname{ind}_2(a)$ for $a = 1, \ldots, 12$:

<table><tr><td>a</td><td>ind₂(a)</td><td>a</td><td>ind₂(a)</td></tr><tr><td>1</td><td>0</td><td>7</td><td>11</td></tr><tr><td>2</td><td>1</td><td>8</td><td>3</td></tr><tr><td>3</td><td>4</td><td>9</td><td>8</td></tr><tr><td>4</td><td>2</td><td>10</td><td>10</td></tr><tr><td>5</td><td>9</td><td>11</td><td>7</td></tr><tr><td>6</td><td>5</td><td>12</td><td>6</td></tr></table>
