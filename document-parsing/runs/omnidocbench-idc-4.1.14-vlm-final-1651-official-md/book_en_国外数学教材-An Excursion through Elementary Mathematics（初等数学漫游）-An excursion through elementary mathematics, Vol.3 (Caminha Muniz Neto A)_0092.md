    $$\begin{array}{l} f ^ {\prime} (x) = \sum_ {n \geq 1} n a _ {n} x ^ {n - 1} = a _ {1} + \sum_ {n \geq 2} n a _ {n} x ^ {n - 1} \\ = a _ {1} + \sum_ {n \geq 2} \left(- a _ {n - 1} + 2 n a _ {n - 2}\right) x ^ {n - 1} \\ = a _ {1} - \sum_ {n \geq 2} a _ {n - 1} x ^ {n - 1} + 2 x \sum_ {n \geq 2} n a _ {n - 2} x ^ {n - 2} \\ = a _ {1} - \left(f (x) - a _ {0}\right) + 2 x \left(\sum_ {n \geq 2} (n - 2) a _ {n - 2} x ^ {n - 2} + 2 \sum_ {n \geq 2} a _ {n - 2} x ^ {n - 2}\right) \\ = a _ {1} + a _ {0} - f (x) + 2 x \left(f ^ {\prime} (x) + 2 f (x)\right). \\ \end{array}$$
  However, since $a_1 + a_0 = 0$, we get $f'(x) = (4x - 1)f(x) + 2xf'(x)$ or, yet,
      $$(2 x - 1) f ^ {\prime} (x) = - (4 x - 1) f (x).$$
  In order to integrate (i.e., to find the solutions of) the above differential equation, note first that $f$ is positive in some interval $(-r, r)$, for some $0 < r \leq \frac{1}{2}$ (this comes from the fact that $f(0) = a_0 = 1 > 0$ and $f$, being differentiable, is continuous, hence has the same sign as $f(0)$ in a suitable neighborhood of 0). Thus, for $|x| < r$ we can write
      $$\frac{f ^ {\prime} (x)}{f (x)} = - \frac{4 x - 1}{2 x - 1} = - 2 - \frac{1}{2 x - 1}$$
  and then, for $|x| < r \leq \frac{1}{2}$ ,
          $$\begin{array}{l} \log f (x) = \log f (t) \bigg | _ {0} ^ {x} = \int_ {0} ^ {x} \frac{f ^ {\prime} (t)}{f (t)} d t \\ = - \int_ {0} ^ {x} \left(2 + \frac{1}{2 t - 1}\right) d t \\ = - 2 x - \frac{1}{2} \log (1 - 2 x). \\ \end{array}$$
  Hence, for $|x| < r \leq \frac{1}{2}$ we have
        $$f (x) = e ^ {- 2 x} (1 - 2 x) ^ {- 1 / 2}. \tag{3.13}$$
Step III: firstly, recall that the power series expansion of $e^{-2x}$ is given by letting $a = -2$ in (3.8), and is valid in the whole real line:
          $$e ^ {- 2 x} = \sum_ {k \geq 0} \frac{(- 2) ^ {k}}{k !} x ^ {k}.$$
