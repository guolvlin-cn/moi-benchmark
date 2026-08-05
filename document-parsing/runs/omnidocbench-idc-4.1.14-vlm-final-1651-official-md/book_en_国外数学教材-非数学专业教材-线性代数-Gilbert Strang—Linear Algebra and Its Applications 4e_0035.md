columns $b_{1}, b_{2}, b_{3}$, the columns of $AB$ should be $Ab_{1}, Ab_{2}, Ab_{3}$!
            $$\text{Multiplicationbycolumns} \qquad A B = A \left[ \begin{array}{l} b _ {1} \\ b _ {2} \\ b _ {3} \end{array} \right] = \left[ \begin{array}{l} A b _ {1} \\ A b _ {2} \\ A b _ {3} \end{array} \right].$$
  Our first requirement had to do with rows, and this one is concerned with columns. A third approach is to describe each individual entry in AB and hope for the best. In fact, there is only one possible rule, and I am not sure who discovered it. It makes everything work. It does not allow us to multiply every pair of matrices. If they are square, they must have the same size. If they are rectangular, they must not have the same shape; the number of columns in A has to equal the number of rows in B . Then A can be multiplied into each column of B .

  If A is m by n , and B is n by p , then multiplication is possible. The product AB will be m by p . We now find the entry in row i and column j of AB .

    1C The i, j entry of AB is the inner product of the i th row of A and the j th column of B . In Figure 1.7, the 3, 2 entry of AB comes from row 3 and column 2:

        $$(A B) _ {3 2} = a _ {3 1} b _ {1 2} + a _ {3 2} b _ {2 2} + a _ {3 3} b _ {3 2} + a _ {3 4} b _ {4 2}. \tag{6}$$
          $$\begin{array}{l} \text{Rowtimes} \\ \text{column} \end{array} A B = \left[ \begin{array}{\text{lll} l} a _ {1 1} & a _ {1 2} & a _ {1 3} & a _ {1 4} \\ a _ {2 1} & a _ {2 2} & a _ {2 3} & a _ {2 4} \\ \boxed{a _ {3 1}} & \boxed{a _ {3 2}} & \boxed{a _ {3 3}} & \boxed{a _ {3 4}} \end{array} \right] \left[ \begin{array}{l l} b _ {1 1} & \boxed{b _ {1 2}} \\ b _ {2 1} & \boxed{b _ {2 2}} \\ b _ {3 1} & \boxed{b _ {3 2}} \\ b _ {4 1} & \boxed{b _ {4 2}} \end{array} \right] = \left[ \begin{array}{l l} * & * \\ * & * \\ * & (A B) _ {3 2} \end{array} \right]$$
      Figure 1.7: A 3 by 4 matrix A times a 4 by 2 matrix B is a 3 by 2 matrix AB .

Note. We write AB when the matrices have nothing special to do with elimination. Our earlier example was EA , because of the elementary matrix E . Later we have PA , or LU , or even LDU . The rule for matrix multiplication stays the same.

Example 1.

    $$A B = \left[ \begin{array}{l l} 2 & 3 \\ 4 & 0 \end{array} \right] \left[ \begin{array}{l l l} 1 & 2 & 0 \\ 5 & - 1 & 0 \end{array} \right] = \left[ \begin{array}{l l l} 1 7 & 1 & 0 \\ 4 & 8 & 0 \end{array} \right].$$
The entry 17 is (2)(1) + (3)(5) , the inner product of the first row of A and first column of B . The entry 8 is (4)(2) + (0)(-1) , from the second row and second column.

  The third column is zero in B , so it is zero in AB . B consists of three columns side by side, and A multiplies each column separately. Every column of AB is a combination of the columns of A . Just as in a matrix-vector multiplication, the columns of A are multiplied by the entries in B .
