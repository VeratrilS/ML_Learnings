"""
Curated starter deck for CS-fundamentals interview prep (Indian SDE placements).

Each entry: (question, answer, tags, difficulty 1-3). Answers are short, interview-ready, plain text;
lines starting with "- " render as bullets. `DECK` flattens everything to dicts with a `subject`.
"""

OS = [
    ("Process vs thread?",
     "Process: an independent program in execution with its own address space, PCB and resources.\n"
     "Thread: a unit of execution inside a process; shares code, data, heap and open files, but has its own stack, registers and PC.\n"
     "- Threads are cheaper to create and switch (no address-space change)\n"
     "- Processes are isolated; a crashing thread can bring down its whole process",
     "process,thread", 1),
    ("What is a PCB (Process Control Block)?",
     "The kernel's data structure for each process. Holds:\n"
     "- PID, process state, program counter, CPU registers\n"
     "- Scheduling info (priority, queue pointers)\n"
     "- Memory info (page table / base-limit registers)\n"
     "- Open files, I/O status, accounting info",
     "process,pcb", 1),
    ("What are the states of a process?",
     "New -> Ready -> Running -> Terminated, plus Waiting (Blocked).\n"
     "- Ready -> Running: dispatched by the scheduler\n"
     "- Running -> Ready: preempted (time slice over / higher priority)\n"
     "- Running -> Waiting: waits for I/O or an event\n"
     "- Waiting -> Ready: I/O or event completes",
     "process,states", 1),
    ("What is a context switch and why is it costly?",
     "Saving the CPU state of the running process/thread into its PCB/TCB and loading the next one's state.\n"
     "It is pure overhead: no useful work happens, and switching processes also changes the address space, "
     "flushing the TLB (unless tagged) and cooling caches. Thread switches within one process are cheaper.",
     "context-switch,scheduling", 2),
    ("User-level vs kernel-level threads?",
     "User-level: managed by a library; fast to create/switch; kernel sees one thread, so one blocking syscall blocks all and no multicore parallelism (many-to-one).\n"
     "Kernel-level: managed and scheduled by the OS; true parallelism on multiple cores; slower to create/switch.\n"
     "Models: many-to-one, one-to-one (Linux, Windows), many-to-many.",
     "thread,kernel", 2),
    ("Preemptive vs non-preemptive scheduling?",
     "Non-preemptive: a process keeps the CPU until it finishes or blocks (FCFS, SJF).\n"
     "Preemptive: the OS can take the CPU away, e.g. on a timer interrupt or a higher-priority arrival (RR, SRTF, preemptive priority).\n"
     "Preemptive gives better response time but needs synchronization of shared data and costs more context switches.",
     "scheduling", 1),
    ("Define turnaround, waiting and response time.",
     "- Turnaround time = completion time - arrival time\n"
     "- Waiting time = turnaround time - burst time (time spent in the ready queue)\n"
     "- Response time = time of first CPU allocation - arrival time\n"
     "Other criteria: CPU utilization and throughput (processes completed per unit time).",
     "scheduling,metrics", 1),
    ("FCFS scheduling and the convoy effect?",
     "FCFS runs processes in arrival order; simple and non-preemptive.\n"
     "Convoy effect: short processes get stuck waiting behind one long CPU-bound process, so average waiting time "
     "is high and I/O devices sit idle.",
     "scheduling,fcfs", 1),
    ("SJF vs SRTF? What is their main problem?",
     "SJF (non-preemptive) picks the job with the shortest next CPU burst; SRTF is its preemptive version "
     "(preempt if a new job has a shorter remaining time).\n"
     "SJF gives the minimum average waiting time (SRTF when preemption is allowed).\n"
     "Problems: burst length must be predicted (exponential averaging), and long jobs can starve.",
     "scheduling,sjf", 2),
    ("How does Round Robin work and how do you choose the quantum?",
     "Each ready process gets a fixed time quantum in circular order; if unfinished it goes to the back of the queue.\n"
     "- Quantum too large -> behaves like FCFS\n"
     "- Quantum too small -> too many context switches\n"
     "Rule of thumb: ~80% of CPU bursts should finish within one quantum. Good response time, no starvation.",
     "scheduling,round-robin", 1),
    ("Priority scheduling: what is starvation and how is it fixed?",
     "The CPU goes to the highest-priority ready process (preemptive or not).\n"
     "Starvation: low-priority processes may wait indefinitely.\n"
     "Fix: aging, i.e. gradually raise the priority of processes that have waited long.",
     "scheduling,starvation", 1),
    ("Multilevel queue vs multilevel feedback queue?",
     "Multilevel queue: ready queue split into fixed queues (e.g. system, interactive, batch), each with its own algorithm; a process stays in its queue.\n"
     "Multilevel feedback queue: processes move between queues. CPU-heavy ones sink to lower-priority queues with larger quanta; "
     "waiting too long moves a process up (aging). Most flexible and general scheduler.",
     "scheduling,mlfq", 2),
    ("What is a race condition?",
     "When multiple threads/processes access shared data concurrently and the final result depends on the timing of their execution.\n"
     "Example: two threads doing count++ (load, add, store) can lose an update.\n"
     "Prevented by making the critical section mutually exclusive (locks, semaphores, atomics).",
     "synchronization,race-condition", 1),
    ("What are the requirements for a critical-section solution?",
     "- Mutual exclusion: at most one process in the critical section\n"
     "- Progress: if none is inside, only those wanting to enter decide who goes next, and the decision can't be postponed forever\n"
     "- Bounded waiting: a limit on how many times others can enter before a waiting process gets its turn",
     "synchronization,critical-section", 2),
    ("Mutex vs semaphore?",
     "Mutex: a locking mechanism with ownership; only the thread that locked it can unlock it. Protects one resource.\n"
     "Semaphore: a signaling mechanism; an integer counter changed by wait (P) and signal (V), with no ownership.\n"
     "- Counting semaphore lets up to N threads in (e.g. a pool of N connections)\n"
     "- Binary semaphore (0/1) is similar to a mutex but any thread may signal it",
     "synchronization,mutex,semaphore", 2),
    ("Define wait() and signal() on a semaphore.",
     "wait(S) / P: decrement S; if S becomes negative (no units left), the caller blocks.\n"
     "signal(S) / V: increment S; if processes are blocked on S, wake one up.\n"
     "Both must execute atomically. The blocking version avoids the busy waiting of the textbook "
     "'while (S <= 0); S--;' definition.",
     "synchronization,semaphore", 2),
    ("Solve producer-consumer (bounded buffer) with semaphores.",
     "Semaphores: mutex = 1, empty = N, full = 0.\n"
     "- Producer: wait(empty); wait(mutex); add item; signal(mutex); signal(full)\n"
     "- Consumer: wait(full); wait(mutex); remove item; signal(mutex); signal(empty)\n"
     "Order matters: doing wait(mutex) before wait(empty/full) can deadlock.",
     "synchronization,producer-consumer", 3),
    ("Explain the readers-writers problem.",
     "Many readers may read together, but a writer needs exclusive access.\n"
     "Classic (readers-preference) solution: read_count, a mutex protecting it, and rw_mutex. "
     "The first reader locks rw_mutex and the last reader releases it; writers lock rw_mutex directly.\n"
     "Drawback: writers can starve; writer-preference or fair variants fix this.",
     "synchronization,readers-writers", 3),
    ("Dining philosophers: how can deadlock happen and how do you avoid it?",
     "Five philosophers, five forks; each needs both neighbouring forks. If all pick up their left fork at once, they all wait forever (circular wait).\n"
     "Fixes:\n"
     "- Allow at most 4 philosophers at the table\n"
     "- Asymmetric order: odd ones pick left first, even ones right first (or always lower-numbered fork first)\n"
     "- Pick up both forks atomically (monitor)",
     "synchronization,deadlock", 2),
    ("What is a spinlock and when is it useful?",
     "A lock where the waiting thread loops (busy-waits) checking the lock instead of sleeping.\n"
     "Useful on multiprocessors when critical sections are very short, since it avoids the cost of a context switch.\n"
     "Wasteful on a single core or for long waits, because it burns CPU time.",
     "synchronization,spinlock", 2),
    ("Explain Peterson's solution.",
     "A software solution for two processes using bool flag[2] and int turn.\n"
     "Entry for Pi: flag[i] = true; turn = j; while (flag[j] && turn == j) wait;\n"
     "Exit: flag[i] = false.\n"
     "Satisfies mutual exclusion, progress and bounded waiting, but can fail on modern CPUs that reorder memory "
     "operations unless memory barriers are used.",
     "synchronization,peterson", 3),
    ("What are the four necessary conditions for deadlock?",
     "The Coffman conditions, which must all hold at once:\n"
     "- Mutual exclusion: a resource can be held by only one process\n"
     "- Hold and wait: a process holds resources while waiting for more\n"
     "- No preemption: resources can't be taken away forcibly\n"
     "- Circular wait: a cycle of processes, each waiting for the next",
     "deadlock", 1),
    ("What are the ways to handle deadlock?",
     "- Prevention: design so one of the four conditions can never hold\n"
     "- Avoidance: grant requests only if the system stays in a safe state (Banker's algorithm)\n"
     "- Detection and recovery: allow deadlock, detect cycles, then kill or preempt processes\n"
     "- Ignore it (ostrich approach): used by most general-purpose OSes like Linux and Windows",
     "deadlock", 1),
    ("How do you prevent deadlock by breaking each condition?",
     "- Mutual exclusion: usually can't be broken (printers, locks are inherently exclusive)\n"
     "- Hold and wait: request all resources at once, or release everything before requesting more\n"
     "- No preemption: if a request fails, release held resources (or let the OS preempt)\n"
     "- Circular wait: impose a global order on resources and always request in increasing order (most practical)",
     "deadlock,prevention", 2),
    ("Explain the Banker's algorithm.",
     "A deadlock-avoidance algorithm. Each process declares Max need; Need = Max - Allocation.\n"
     "Safety check: Work = Available; repeatedly find a process with Need <= Work, assume it finishes "
     "(Work += its Allocation) and mark it done. If all finish, the state is safe and the order is a safe sequence.\n"
     "A request is granted only if the resulting state is still safe. Cost: O(m * n^2) for n processes, m resource types.",
     "deadlock,bankers", 3),
    ("Safe state vs unsafe state?",
     "Safe: there is at least one ordering (safe sequence) in which every process can get its maximum need and finish.\n"
     "Unsafe: no such sequence exists. An unsafe state is not necessarily deadlocked, but it may lead to deadlock.\n"
     "Every deadlocked state is unsafe.",
     "deadlock,bankers", 2),
    ("When does a cycle in a resource-allocation graph mean deadlock?",
     "- If every resource type has a single instance: a cycle means deadlock (necessary and sufficient)\n"
     "- If resource types have multiple instances: a cycle is necessary but not sufficient\n"
     "With single instances, detection uses a wait-for graph (processes only) and checks it for cycles.",
     "deadlock,rag", 2),
    ("Deadlock vs starvation?",
     "Deadlock: a set of processes wait on each other forever and none can proceed; it needs a circular wait.\n"
     "Starvation: one process waits indefinitely while others keep progressing (e.g. low priority).\n"
     "Starvation is fixed with aging or fair scheduling; deadlock needs prevention, avoidance or recovery.",
     "deadlock,starvation", 1),
    ("Logical vs physical address? What is the MMU?",
     "Logical (virtual) address: generated by the CPU, as seen by the program.\n"
     "Physical address: the actual location in RAM.\n"
     "The MMU (Memory Management Unit) is hardware that translates logical to physical addresses at run time, "
     "using relocation registers or page tables.",
     "memory,mmu", 1),
    ("Internal vs external fragmentation?",
     "Internal: wasted space inside an allocated block (block bigger than requested), e.g. the unused part of the last page.\n"
     "External: enough total free memory exists but it is split into non-contiguous holes.\n"
     "Paging removes external fragmentation (internal remains); compaction or paging fixes external fragmentation.",
     "memory,fragmentation", 1),
    ("How does paging work?",
     "Physical memory is divided into fixed-size frames and logical memory into same-size pages.\n"
     "A logical address = (page number, offset). The page table maps page number -> frame number, "
     "and physical address = frame base + offset.\n"
     "Pros: no external fragmentation, non-contiguous allocation. Cons: page-table memory, internal fragmentation, extra memory access.",
     "memory,paging", 2),
    ("What is a TLB? Give the effective access time formula.",
     "The Translation Lookaside Buffer is a small, fast associative cache of recent page-table entries.\n"
     "With hit ratio h, TLB time t and memory time m (single-level page table):\n"
     "EAT = h * (t + m) + (1 - h) * (t + 2m)\n"
     "A TLB miss needs one extra memory access to read the page table.",
     "memory,tlb", 2),
    ("Paging vs segmentation?",
     "- Paging: fixed-size pages, invisible to the programmer, no external but some internal fragmentation\n"
     "- Segmentation: variable-size logical units (code, stack, heap), matches the programmer's view, "
     "allows per-segment protection/sharing, but suffers external fragmentation\n"
     "Segmented paging combines both (segments are themselves paged).",
     "memory,paging,segmentation", 2),
    ("Why use multi-level or inverted page tables?",
     "A flat page table for a large address space is huge (32-bit, 4 KB pages: 2^20 entries per process).\n"
     "- Multi-level (hierarchical): page the page table, so only the used parts exist in memory\n"
     "- Inverted: one entry per physical frame for the whole system (pid, page), which saves memory but makes lookup slower (hashing used)",
     "memory,paging", 3),
    ("What is virtual memory and demand paging?",
     "Virtual memory lets a process use an address space larger than physical RAM by keeping only the needed pages in memory "
     "and the rest on disk.\n"
     "Demand paging loads a page only when it is first accessed. Benefits: more processes in memory, larger programs, faster start-up.",
     "memory,virtual-memory", 2),
    ("What happens on a page fault?",
     "1. The access hits a page-table entry marked invalid, so the hardware traps to the OS\n"
     "2. The OS checks the reference is legal (otherwise it kills the process)\n"
     "3. It finds a free frame, or picks a victim with page replacement (writing it back if dirty)\n"
     "4. It reads the page from disk into the frame and updates the page table\n"
     "5. It restarts the faulting instruction",
     "memory,page-fault", 2),
    ("Compare FIFO, Optimal and LRU page replacement.",
     "- FIFO: evict the oldest loaded page; simple, but suffers Belady's anomaly\n"
     "- Optimal (OPT): evict the page used farthest in the future; fewest faults but impossible to implement, used as a benchmark\n"
     "- LRU: evict the least recently used page; good approximation of OPT, costly to do exactly "
     "(counters or a stack), so approximated by Clock / Second-Chance using a reference bit",
     "memory,page-replacement", 2),
    ("What is Belady's anomaly?",
     "With FIFO, giving a process more frames can increase the number of page faults.\n"
     "Classic string 1,2,3,4,1,2,5,1,2,3,4,5: 3 frames -> 9 faults, 4 frames -> 10 faults.\n"
     "Stack algorithms such as LRU and Optimal never show this anomaly.",
     "memory,page-replacement,belady", 2),
    ("What is thrashing and how do you handle it?",
     "Thrashing is when a process spends more time paging than executing, because its working set doesn't fit in its frames.\n"
     "CPU utilization falls, the scheduler adds more processes, and it gets worse.\n"
     "Fixes: working-set model, page-fault-frequency control (give more frames / suspend processes), lower the degree of multiprogramming, add RAM.",
     "memory,thrashing", 2),
    ("What IPC mechanisms exist?",
     "- Shared memory: fastest; after setup there are no kernel calls, but it needs explicit synchronization\n"
     "- Message passing: pipes (parent-child), named pipes/FIFOs, message queues, sockets (even across machines)\n"
     "- Signals: asynchronous notifications\n"
     "Message passing is easier and safer; shared memory is faster for large data.",
     "ipc", 1),
    ("What does fork() return, and how many processes do n forks create?",
     "fork() creates a child process that is a copy of the parent. It returns 0 in the child, the child's PID in the parent, and -1 on failure.\n"
     "n fork() calls in sequence give 2^n processes in total (2^n - 1 new children).\n"
     "Modern OSes use copy-on-write: pages are shared until one side writes. exec() replaces the process image.",
     "process,fork", 2),
    ("Zombie vs orphan process?",
     "Zombie: a child that has exited, but whose parent hasn't called wait() yet. Its PCB/exit status remains in the process table.\n"
     "Orphan: a child whose parent exited first. It is adopted by init/systemd (PID 1), which reaps it.\n"
     "Too many zombies can exhaust PIDs.",
     "process,zombie", 2),
    ("User mode vs kernel mode? What is a system call?",
     "Kernel mode can run privileged instructions and access all memory; user mode is restricted.\n"
     "A system call is how a user program asks the kernel for a service (read, write, fork, open). "
     "It traps into kernel mode via a software interrupt/syscall instruction, the kernel does the work, then returns to user mode.",
     "kernel,system-call", 1),
    ("Monolithic kernel vs microkernel?",
     "Monolithic: all OS services (file system, drivers, memory, scheduling) run in kernel space; fast, but a buggy driver can crash everything (Linux).\n"
     "Microkernel: only the essentials (IPC, scheduling, basic memory) in the kernel; other services run as user-space servers. "
     "More reliable and modular, but IPC overhead makes it slower (Minix, QNX).",
     "kernel", 2),
    ("Compare disk scheduling algorithms.",
     "- FCFS: fair but high seek time\n"
     "- SSTF: nearest request first; low seek time but can starve far requests\n"
     "- SCAN (elevator): sweep end to end, serving requests on the way\n"
     "- C-SCAN: serve in one direction only, then jump back; more uniform wait\n"
     "- LOOK / C-LOOK: like SCAN/C-SCAN but turn at the last request, not the disk end",
     "disk,scheduling", 2),
    ("Interrupt vs polling?",
     "Polling: the CPU repeatedly checks a device's status; simple but wastes cycles.\n"
     "Interrupt: the device signals the CPU when ready, and the CPU runs an interrupt service routine. Efficient for infrequent events.\n"
     "For very high-rate devices, polling (or DMA plus interrupts) can beat per-event interrupts.",
     "interrupts,io", 1),
]

DBMS = [
    ("DBMS vs file system?",
     "A DBMS adds what plain files lack:\n"
     "- Less redundancy and inconsistency (normalized, integrity constraints)\n"
     "- Concurrent access control and transactions (ACID)\n"
     "- Crash recovery, security/authorization\n"
     "- A declarative query language (SQL) and indexing for fast access",
     "basics", 1),
    ("What are the ACID properties?",
     "- Atomicity: all operations of a transaction happen or none do\n"
     "- Consistency: a transaction takes the DB from one valid state to another (constraints hold)\n"
     "- Isolation: concurrent transactions don't see each other's intermediate states\n"
     "- Durability: once committed, changes survive crashes",
     "transactions,acid", 1),
    ("How do databases implement atomicity and durability?",
     "Using logging, typically Write-Ahead Logging (WAL): a log record is written to stable storage before the data page.\n"
     "- Undo using old values in the log rolls back uncommitted transactions (atomicity)\n"
     "- Redo using new values replays committed transactions after a crash (durability)\n"
     "Alternative: shadow paging. Checkpoints limit how much log must be scanned.",
     "transactions,recovery,wal", 2),
    ("What are the states of a transaction?",
     "Active -> Partially committed (last statement executed) -> Committed.\n"
     "If something fails: Active/Partially committed -> Failed -> Aborted (rolled back), then it can be restarted or killed.\n"
     "Committed or aborted transactions are terminated.",
     "transactions", 1),
    ("Explain super, candidate, primary, alternate and foreign keys.",
     "- Super key: any set of attributes that uniquely identifies a row\n"
     "- Candidate key: a minimal super key\n"
     "- Primary key: the chosen candidate key (unique, NOT NULL)\n"
     "- Alternate key: the candidate keys not chosen as primary\n"
     "- Foreign key: attribute(s) referencing a primary/unique key in another table (referential integrity)\n"
     "- Composite key: a key made of more than one column",
     "keys", 1),
    ("Primary key vs unique key?",
     "- Primary key: only one per table, cannot be NULL; in MySQL InnoDB and SQL Server it is the clustered index by default\n"
     "- Unique key: many per table, allows NULLs (MySQL and Postgres allow multiple NULLs; SQL Server allows one); non-clustered index by default",
     "keys,constraints", 1),
    ("Why do we normalize? What anomalies does it remove?",
     "Normalization splits tables to remove redundancy based on functional dependencies.\n"
     "It removes:\n"
     "- Insertion anomaly: can't insert data without unrelated data\n"
     "- Update anomaly: the same fact stored in many rows can become inconsistent\n"
     "- Deletion anomaly: deleting a row loses other, unrelated facts",
     "normalization", 1),
    ("What is 1NF?",
     "A relation is in 1NF if every attribute holds atomic (indivisible) values: no multivalued attributes, "
     "no repeating groups or nested tables, and each row is unique.\n"
     "Example: a phone column holding '98..., 99...' violates 1NF; store one phone per row or use a separate table.",
     "normalization,1nf", 1),
    ("What is 2NF?",
     "1NF plus no partial dependency: no non-prime attribute depends on only part of a candidate key.\n"
     "It only matters with composite keys. Example: in (student_id, course_id, student_name), student_name depends only on "
     "student_id, so move it to a Student table.",
     "normalization,2nf", 2),
    ("What is 3NF?",
     "2NF plus no transitive dependency of a non-prime attribute on a key.\n"
     "Formal: for every FD X -> A, either X is a super key or A is a prime attribute (part of some candidate key).\n"
     "Example: emp_id -> dept_id -> dept_name; move dept_name to a Department table.",
     "normalization,3nf", 2),
    ("What is BCNF and how is it different from 3NF?",
     "BCNF: for every non-trivial FD X -> Y, X must be a super key. It drops 3NF's 'A is prime' exception, so it is stricter.\n"
     "- 3NF decomposition: always lossless and dependency-preserving\n"
     "- BCNF decomposition: always lossless, but may not preserve all dependencies\n"
     "Every BCNF relation is in 3NF, but not vice versa.",
     "normalization,bcnf", 3),
    ("What is a functional dependency? State Armstrong's axioms.",
     "X -> Y means that two tuples agreeing on X must also agree on Y (X determines Y).\n"
     "Armstrong's axioms (sound and complete):\n"
     "- Reflexivity: if Y is a subset of X, then X -> Y\n"
     "- Augmentation: if X -> Y, then XZ -> YZ\n"
     "- Transitivity: if X -> Y and Y -> Z, then X -> Z\n"
     "Derived rules: union, decomposition, pseudo-transitivity.",
     "normalization,fd", 2),
    ("How do you find candidate keys using attribute closure?",
     "Compute X+ (all attributes determined by X) by repeatedly applying the FDs. If X+ contains all attributes, X is a super key; "
     "if no proper subset also is, X is a candidate key.\n"
     "Tip: attributes that never appear on the right side of any FD must be in every key.\n"
     "Example: R(A,B,C,D), A->B, B->C, C->D: A+ = ABCD, so A is the only candidate key.",
     "normalization,closure,keys", 2),
    ("When is a decomposition lossless?",
     "Decomposing R into R1 and R2 is lossless (natural join gives back exactly R) if the common attributes form a key of at least one part:\n"
     "R1 ∩ R2 -> R1 or R1 ∩ R2 -> R2.\n"
     "A lossy decomposition produces spurious tuples on join.",
     "normalization,decomposition", 3),
    ("What is denormalization and when would you use it?",
     "Intentionally adding redundancy (duplicated columns, precomputed aggregates, merged tables) to avoid expensive joins.\n"
     "Used in read-heavy systems, reporting/OLAP and NoSQL designs.\n"
     "Cost: more storage, slower writes and a risk of inconsistency (must be kept in sync).",
     "normalization,denormalization", 1),
    ("What is a multivalued dependency and 4NF?",
     "X ->> Y: for a value of X, the set of Y values is independent of the other attributes.\n"
     "Example: a student's courses and hobbies stored in one table creates every combination of the two.\n"
     "4NF: BCNF plus no non-trivial MVD unless X is a super key. Fix by splitting into (student, course) and (student, hobby).",
     "normalization,4nf", 3),
    ("What are the main components of an ER model?",
     "- Entity (rectangle) and entity set; weak entity (double rectangle)\n"
     "- Attributes (ellipses): simple/composite, single/multivalued (double ellipse), derived (dashed), key (underlined)\n"
     "- Relationships (diamond) with cardinality 1:1, 1:N, M:N and participation (total = double line, partial)\n"
     "- Extended ER: specialization, generalization, aggregation",
     "er-model", 1),
    ("What is a weak entity?",
     "An entity without a primary key of its own. It is identified by its owner's key plus its own partial key (discriminator).\n"
     "It has total participation in an identifying relationship (double diamond).\n"
     "Example: Dependent (name) of Employee, identified by (emp_id, dependent_name).",
     "er-model,weak-entity", 2),
    ("How do you convert ER relationships to tables?",
     "- 1:1: put a foreign key on either side (prefer the total-participation side)\n"
     "- 1:N: put the foreign key on the N side\n"
     "- M:N: create a separate table whose key is both foreign keys (plus relationship attributes)\n"
     "- Multivalued attribute: a separate table (entity key, value)\n"
     "- Weak entity: table with owner's PK + partial key as its PK",
     "er-model,schema", 2),
    ("Explain the SQL isolation levels and what each prevents.",
     "- Read Uncommitted: dirty reads possible\n"
     "- Read Committed: no dirty reads; non-repeatable reads possible\n"
     "- Repeatable Read: no non-repeatable reads; phantoms possible per the SQL standard (InnoDB mostly prevents them)\n"
     "- Serializable: none of these anomalies\n"
     "Defaults: MySQL InnoDB is Repeatable Read; PostgreSQL, Oracle and SQL Server are Read Committed.",
     "transactions,isolation", 2),
    ("Dirty read vs non-repeatable read vs phantom read?",
     "- Dirty read: reading another transaction's uncommitted change (which may roll back)\n"
     "- Non-repeatable read: re-reading the same row gives a different value because another transaction updated it and committed\n"
     "- Phantom read: re-running a range query returns new/missing rows because another transaction inserted/deleted rows",
     "transactions,isolation,anomalies", 2),
    ("What is the lost update problem?",
     "Two transactions read the same value and both write back based on it; the second write overwrites the first.\n"
     "Example: both read balance 100, T1 writes 150, T2 writes 80; T1's update is lost.\n"
     "Prevent with locking (SELECT ... FOR UPDATE), optimistic concurrency (version column), atomic updates (SET x = x + 50) or a strict isolation level.",
     "transactions,concurrency", 2),
    ("Conflict vs view serializability? How do you test conflict serializability?",
     "A schedule is serializable if it is equivalent to some serial schedule.\n"
     "- Conflict serializable: can be turned into a serial schedule by swapping non-conflicting adjacent operations\n"
     "- View serializable: same reads-from relations and same final writes (a broader class; includes blind writes)\n"
     "Test: build a precedence graph (Ti -> Tj if Ti's operation conflicts with and precedes Tj's). Acyclic means conflict serializable.",
     "transactions,serializability", 3),
    ("When do two operations conflict?",
     "When all three hold:\n"
     "- They belong to different transactions\n"
     "- They access the same data item\n"
     "- At least one of them is a write\n"
     "So R-W, W-R and W-W conflict; R-R never does.",
     "transactions,serializability", 2),
    ("Recoverable vs cascadeless vs strict schedules?",
     "- Recoverable: if Tj reads data written by Ti, Ti commits before Tj commits\n"
     "- Cascadeless: transactions read only committed data, so one abort doesn't cascade into others\n"
     "- Strict: no read or write of an item until the last transaction that wrote it commits/aborts\n"
     "Strict ⊂ cascadeless ⊂ recoverable.",
     "transactions,recovery", 3),
    ("Explain two-phase locking (2PL) and its variants.",
     "Each transaction has a growing phase (acquire locks, release none) then a shrinking phase (release locks, acquire none).\n"
     "Guarantees conflict serializability, but not freedom from deadlock or cascading aborts.\n"
     "- Strict 2PL: hold exclusive locks until commit/abort (no cascading aborts; most common)\n"
     "- Rigorous 2PL: hold all locks until commit",
     "concurrency,locking,2pl", 2),
    ("Shared vs exclusive locks?",
     "- Shared (S) lock: for reading; many transactions can hold S on the same item\n"
     "- Exclusive (X) lock: for writing; no other lock can coexist\n"
     "Compatibility: only S-S is compatible. Lock upgrade S -> X is allowed in the growing phase.",
     "concurrency,locking", 1),
    ("Explain the timestamp-ordering protocol.",
     "Each transaction gets a timestamp TS; each item keeps read_TS and write_TS. Conflicting operations must execute in timestamp order.\n"
     "- Read(X) by T: if TS(T) < write_TS(X), abort T\n"
     "- Write(X) by T: if TS(T) < read_TS(X) or TS(T) < write_TS(X), abort T\n"
     "Deadlock-free (no waiting), but may cause many restarts. Thomas write rule ignores obsolete writes instead of aborting.",
     "concurrency,timestamp", 3),
    ("Wait-die vs wound-wait deadlock prevention?",
     "Both use transaction timestamps (older = smaller TS).\n"
     "- Wait-die (non-preemptive): an older requester waits; a younger requester dies (rolls back)\n"
     "- Wound-wait (preemptive): an older requester wounds (aborts) the younger holder; a younger requester waits\n"
     "Restarted transactions keep their original timestamps, so no starvation.",
     "concurrency,deadlock", 3),
    ("What is MVCC?",
     "Multi-Version Concurrency Control keeps multiple versions of each row. Readers see a consistent snapshot as of their start "
     "and never block writers; writers don't block readers.\n"
     "Used by PostgreSQL, MySQL InnoDB and Oracle. Old versions are cleaned up later (VACUUM in Postgres, purge in InnoDB).",
     "concurrency,mvcc", 3),
    ("What is an index and what does it cost?",
     "An auxiliary data structure (usually a B+ tree) that speeds up lookups and range queries, avoiding full table scans: O(log n) instead of O(n).\n"
     "Costs: extra storage, slower INSERT/UPDATE/DELETE (the index must be maintained). Index columns used in WHERE, JOIN and ORDER BY with good selectivity.",
     "indexing", 1),
    ("Clustered vs non-clustered index?",
     "- Clustered: determines the physical order of rows; the leaf level holds the data itself. Only one per table (InnoDB: the primary key)\n"
     "- Non-clustered (secondary): a separate structure whose leaves hold key + pointer (or the PK in InnoDB) to the row. Many per table; may need an extra lookup\n"
     "A covering index contains all the columns a query needs, so no extra lookup is required.",
     "indexing,clustered", 2),
    ("B-tree vs B+ tree? Why do databases use B+ trees?",
     "- B-tree: keys and data in all nodes\n"
     "- B+ tree: data (or row pointers) only in leaves; internal nodes hold keys only; leaves are linked\n"
     "B+ tree benefits: higher fan-out so the tree is shallower (fewer disk I/Os), fast range scans by walking the leaf list, "
     "and uniform search cost (always to a leaf).",
     "indexing,b-plus-tree", 2),
    ("Why not use a hash index or a BST instead of a B+ tree?",
     "- Hash index: O(1) for equality, but useless for range queries, ORDER BY and prefix matches\n"
     "- BST/AVL: binary fan-out gives a tall tree, so one disk I/O per level is too many\n"
     "B+ trees are wide (hundreds of keys per node), so a 3-4 level tree can index millions of rows.",
     "indexing,b-plus-tree", 2),
    ("What is the leftmost-prefix rule for composite indexes?",
     "An index on (a, b, c) is sorted by a, then b, then c. It can be used for filters on a, (a, b) or (a, b, c), "
     "but not for b alone or (b, c).\n"
     "A range condition on a column stops the use of later columns for seeking. Put equality, high-selectivity columns first.",
     "indexing,composite", 2),
    ("When does a query fail to use an index?",
     "- A function or expression on the column: WHERE YEAR(created) = 2025\n"
     "- A leading wildcard: LIKE '%abc'\n"
     "- Implicit type conversion (comparing a string column to a number)\n"
     "- Low selectivity (the optimizer prefers a full scan)\n"
     "- OR across different columns, or ignoring the leftmost-prefix rule\n"
     "Check with EXPLAIN.",
     "indexing,performance", 2),
    ("DELETE vs TRUNCATE vs DROP?",
     "- DELETE (DML): removes selected rows with WHERE, logged row by row, fires triggers, can be rolled back\n"
     "- TRUNCATE (DDL): removes all rows quickly (deallocates pages), resets identity, no WHERE, no row triggers\n"
     "- DROP (DDL): removes the whole table: data, structure, indexes and constraints\n"
     "TRUNCATE/DROP auto-commit in MySQL/Oracle but are transactional in PostgreSQL.",
     "sql,ddl", 1),
    ("View vs materialized view?",
     "- View: a saved query (virtual table); runs each time it is queried; always current; used for security and simplicity\n"
     "- Materialized view: stores the query result physically; fast reads, but must be refreshed and can be stale\n"
     "Use materialized views for expensive aggregations in reporting.",
     "views", 2),
    ("Stored procedure vs function vs trigger?",
     "- Stored procedure: precompiled SQL called explicitly (CALL); may return zero or more values via OUT params; can do DML and transactions\n"
     "- Function: must return a value, can be used inside SELECT, usually shouldn't modify data\n"
     "- Trigger: runs automatically BEFORE/AFTER INSERT/UPDATE/DELETE; used for auditing and enforcing rules",
     "procedures,triggers", 2),
    ("SQL vs NoSQL? What is the CAP theorem?",
     "SQL: relational, fixed schema, joins, ACID, usually scales vertically. NoSQL: key-value, document, column-family or graph; "
     "flexible schema, scales horizontally, often BASE/eventual consistency.\n"
     "CAP: during a network partition (P), a distributed system must choose Consistency or Availability. "
     "E.g. HBase is CP, Cassandra/DynamoDB are AP (tunable).",
     "nosql,cap", 2),
    ("Replication vs partitioning vs sharding?",
     "- Replication: copies of the same data on several nodes; gives read scaling and fault tolerance (leader-follower or multi-leader)\n"
     "- Partitioning: splitting a table into pieces (by range/hash/list); can be within one server\n"
     "- Sharding: horizontal partitioning across multiple servers, each holding a subset of rows; gives write scaling but makes cross-shard joins and transactions hard",
     "scaling,sharding", 2),
    ("What are the basic relational algebra operations?",
     "- Selection σ (filter rows), Projection π (choose columns)\n"
     "- Union ∪, Set difference −, Cartesian product ×, Rename ρ (these six are fundamental)\n"
     "- Derived: intersection ∩, joins ⋈ (natural, theta, outer), division ÷ (for 'for all' queries)",
     "relational-algebra", 2),
    ("What is a checkpoint in DBMS recovery?",
     "A point where the DBMS flushes dirty buffers and log records to disk and writes a checkpoint record to the log.\n"
     "On crash recovery, only transactions active at or after the last checkpoint need undo/redo, which shortens recovery time.",
     "recovery,checkpoint", 2),
    ("DDL vs DML vs DCL vs TCL?",
     "- DDL (definition): CREATE, ALTER, DROP, TRUNCATE, RENAME\n"
     "- DML (manipulation): SELECT, INSERT, UPDATE, DELETE (SELECT is sometimes listed separately as DQL)\n"
     "- DCL (control): GRANT, REVOKE\n"
     "- TCL (transaction control): COMMIT, ROLLBACK, SAVEPOINT",
     "sql,basics", 1),
]

CN = [
    ("Name the OSI layers and their jobs.",
     "7 Application (HTTP, DNS) - services to apps\n"
     "6 Presentation - encoding, encryption, compression\n"
     "5 Session - set up/manage sessions\n"
     "4 Transport (TCP/UDP) - end-to-end delivery, ports; segments\n"
     "3 Network (IP) - logical addressing and routing; packets\n"
     "2 Data Link (Ethernet, MAC) - hop-to-hop framing, error detection; frames\n"
     "1 Physical - bits on the medium",
     "osi,layers", 1),
    ("OSI vs TCP/IP model?",
     "TCP/IP has 4 layers (some texts say 5): Application (= OSI 5-7), Transport, Internet (= Network), Network Access/Link (= Data Link + Physical).\n"
     "OSI is a reference model, designed before its protocols; TCP/IP is the practical model the Internet actually uses, built around its protocols.",
     "osi,tcp-ip", 1),
    ("Hub vs switch vs router?",
     "- Hub (L1): repeats bits to all ports; one collision domain\n"
     "- Switch (L2): forwards frames by MAC address using a MAC table; each port is its own collision domain, but there is one broadcast domain (unless VLANs are used)\n"
     "- Router (L3): forwards packets between networks by IP using a routing table; separates broadcast domains",
     "devices", 1),
    ("TCP vs UDP?",
     "TCP: connection-oriented, reliable (ACKs, retransmission), in-order byte stream, flow and congestion control; 20-60 byte header. Used for HTTP, SSH, email.\n"
     "UDP: connectionless, no guarantees, message-oriented, 8-byte header, low latency. Used for DNS, video/voice, gaming, and QUIC (HTTP/3) on top.",
     "tcp,udp,transport", 1),
    ("Explain the TCP three-way handshake. Why three steps?",
     "1. Client -> SYN, seq = x\n"
     "2. Server -> SYN-ACK, seq = y, ack = x + 1\n"
     "3. Client -> ACK, ack = y + 1\n"
     "Three steps let both sides choose and confirm each other's initial sequence numbers, and stop delayed duplicate SYNs from opening stale connections.",
     "tcp,handshake", 2),
    ("How is a TCP connection closed? Why TIME_WAIT?",
     "Four-way: FIN -> ACK, then the other side sends FIN -> ACK (each direction closes separately; a half-close is possible).\n"
     "The side that closes first waits in TIME_WAIT for 2*MSL so that its final ACK can be resent if lost, "
     "and so old delayed segments die before the same port pair is reused.",
     "tcp,termination", 2),
    ("Flow control vs congestion control?",
     "- Flow control: protects the receiver. The receiver advertises its window (rwnd) and the sender never has more than rwnd unacknowledged bytes\n"
     "- Congestion control: protects the network. The sender limits itself with cwnd, inferred from loss/delay\n"
     "Effective window = min(rwnd, cwnd).",
     "tcp,flow-control,congestion", 2),
    ("Sliding window: Go-Back-N vs Selective Repeat?",
     "Both allow several unacknowledged frames in flight.\n"
     "- Go-Back-N: cumulative ACKs; on a loss/timeout, resend that frame and all after it; receiver window = 1; sender window <= 2^m - 1\n"
     "- Selective Repeat: individual ACKs; resend only lost frames; receiver buffers out-of-order frames; window <= 2^(m-1)\n"
     "(m = number of sequence-number bits)",
     "data-link,sliding-window", 2),
    ("How does TCP congestion control work?",
     "- Slow start: cwnd starts at ~1 MSS (larger in modern stacks) and doubles every RTT until ssthresh\n"
     "- Congestion avoidance: then cwnd grows by ~1 MSS per RTT (additive increase)\n"
     "- Timeout: ssthresh = cwnd / 2, cwnd = 1 MSS, back to slow start\n"
     "- 3 duplicate ACKs: fast retransmit; Reno does fast recovery, ssthresh = cwnd / 2 and cwnd ≈ ssthresh (multiplicative decrease)\n"
     "This is AIMD. Modern defaults: CUBIC, BBR.",
     "tcp,congestion", 3),
    ("How does TCP guarantee reliable delivery?",
     "- Sequence numbers on every byte, for ordering and duplicate detection\n"
     "- Cumulative ACKs (plus SACK) and retransmission on timeout or 3 duplicate ACKs\n"
     "- Checksum to detect corruption\n"
     "- Flow control (receive window) and congestion control\n"
     "- Connection setup/teardown to synchronize state",
     "tcp,reliability", 1),
    ("How does DNS resolution work?",
     "Browser cache -> OS cache / hosts file -> recursive resolver (ISP or 8.8.8.8). On a miss the resolver asks a root server -> TLD server (.com) -> "
     "authoritative server, which returns the record. Answers are cached for their TTL.\n"
     "Uses UDP port 53 (TCP for large responses and zone transfers).\n"
     "Records: A (IPv4), AAAA (IPv6), CNAME (alias), MX (mail), NS, TXT.",
     "dns,application", 2),
    ("What happens when you type a URL and press Enter?",
     "1. URL parsed; HSTS / browser cache checked\n"
     "2. DNS resolves the domain to an IP\n"
     "3. TCP three-way handshake (or QUIC over UDP), then the TLS handshake for HTTPS\n"
     "4. HTTP request sent; it may pass through a CDN or load balancer to a server, which builds the response\n"
     "5. Browser parses HTML, fetches CSS/JS/images, builds DOM + CSSOM, runs layout, paints\n"
     "Under the hood: ARP for the gateway's MAC, NAT, routing hop by hop.",
     "dns,http,tcp,browser", 2),
    ("HTTP vs HTTPS?",
     "HTTPS is HTTP over TLS: encryption (confidentiality), integrity (tamper detection) and server authentication through certificates.\n"
     "HTTP uses port 80 and sends plaintext; HTTPS uses port 443.\n"
     "Cost: a TLS handshake (1-RTT in TLS 1.3) and a bit of CPU, which is negligible today.",
     "http,https,security", 1),
    ("Walk through the TLS handshake.",
     "1. ClientHello: supported versions and cipher suites, a random value (and a key share in TLS 1.3)\n"
     "2. ServerHello: chosen cipher and the server's key share, plus its certificate (and a signature proving it owns the key)\n"
     "3. Client verifies the certificate chain up to a trusted CA and checks the hostname\n"
     "4. Both derive the same session keys via (EC)DHE, giving forward secrecy; Finished messages confirm\n"
     "Then data is encrypted with fast symmetric ciphers (AES-GCM / ChaCha20). TLS 1.3 takes 1 RTT (0-RTT on resumption).",
     "tls,https,security", 3),
    ("Symmetric vs asymmetric encryption?",
     "- Symmetric: the same key encrypts and decrypts (AES); fast, but the key must be shared securely\n"
     "- Asymmetric: a public/private key pair (RSA, ECC); slow; used for key exchange and digital signatures\n"
     "TLS uses asymmetric crypto to authenticate and agree on a key, then symmetric crypto for the bulk data.",
     "security,encryption", 1),
    ("Which HTTP methods are safe and which are idempotent?",
     "- Safe (no state change): GET, HEAD, OPTIONS\n"
     "- Idempotent (repeating has the same effect): GET, HEAD, OPTIONS, PUT, DELETE\n"
     "- Not idempotent: POST (creates a new resource each time); PATCH is not guaranteed to be idempotent\n"
     "PUT replaces a resource; PATCH partially updates it.",
     "http,rest", 1),
    ("Explain common HTTP status codes.",
     "1xx info, 2xx success, 3xx redirect, 4xx client error, 5xx server error.\n"
     "- 200 OK, 201 Created, 204 No Content\n"
     "- 301 Moved Permanently, 302 Found (temporary), 304 Not Modified\n"
     "- 400 Bad Request, 401 Unauthorized (not authenticated), 403 Forbidden (no permission), 404 Not Found, 429 Too Many Requests\n"
     "- 500 Internal Error, 502 Bad Gateway, 503 Service Unavailable, 504 Gateway Timeout",
     "http,status-codes", 1),
    ("HTTP/1.1 vs HTTP/2 vs HTTP/3?",
     "- HTTP/1.1: text-based, persistent (keep-alive) connections, but one request at a time per connection, so head-of-line blocking\n"
     "- HTTP/2: binary framing, multiplexed streams on one TCP connection, header compression (HPACK), server push; TCP-level HOL blocking remains\n"
     "- HTTP/3: runs on QUIC over UDP; independent streams (no transport HOL blocking), TLS 1.3 built in, faster setup, connection migration",
     "http,http2,http3", 2),
    ("Cookies vs sessions vs JWT?",
     "- Cookie: small data the server asks the browser to store and send back on every request (flags: HttpOnly, Secure, SameSite)\n"
     "- Session: state kept on the server; the cookie holds only a session ID. Easy to revoke, but needs shared storage to scale\n"
     "- JWT: signed, self-contained token (header.payload.signature); stateless and scalable, but hard to revoke before expiry",
     "http,auth", 2),
    ("IPv4 vs IPv6?",
     "- Address size: 32 bits (~4.3 billion) vs 128 bits\n"
     "- Notation: dotted decimal vs hexadecimal with colons\n"
     "- IPv6: no NAT needed, simpler fixed 40-byte header, no checksum, no fragmentation by routers, built-in SLAAC autoconfiguration, IPsec support\n"
     "- IPv6 has no broadcast (uses multicast) and uses NDP instead of ARP",
     "ip,ipv6", 1),
    ("IPv4 address classes and private ranges?",
     "- A: 1-126, default /8 (127 is loopback)\n"
     "- B: 128-191, /16\n"
     "- C: 192-223, /24\n"
     "- D: 224-239 multicast; E: 240-255 reserved\n"
     "Private (RFC 1918): 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16. Classless CIDR has replaced classes in practice.",
     "ip,addressing", 1),
    ("Subnetting: how many hosts in a /26? What are the subnets of 192.168.1.0/26?",
     "/26 leaves 32 - 26 = 6 host bits: 2^6 = 64 addresses, 64 - 2 = 62 usable hosts (network and broadcast excluded).\n"
     "Mask 255.255.255.192. Subnets: .0, .64, .128, .192.\n"
     "First subnet: network 192.168.1.0, hosts .1-.62, broadcast .63.",
     "ip,subnetting", 2),
    ("What is CIDR?",
     "Classless Inter-Domain Routing writes a network as address/prefix-length (e.g. 10.1.0.0/16) instead of fixed classes.\n"
     "It allows variable-length subnet masks (VLSM) and route aggregation (supernetting: several contiguous networks advertised as one prefix), "
     "which saves addresses and shrinks routing tables. Routers pick the longest prefix match.",
     "ip,cidr", 2),
    ("What is NAT and why is it used?",
     "Network Address Translation rewrites private source IPs (and ports) to a public IP at the router, so many devices share one public address.\n"
     "PAT/NAPT (overload) tracks connections by port number.\n"
     "It saves IPv4 addresses and hides internal hosts, but breaks end-to-end connectivity (needs port forwarding / NAT traversal).",
     "ip,nat", 2),
    ("What does ARP do?",
     "ARP resolves an IPv4 address to a MAC address within the local network.\n"
     "The host broadcasts 'Who has IP X?'; the owner replies by unicast with its MAC; the result is cached in the ARP table.\n"
     "For an IP outside the subnet, the host ARPs for the default gateway's MAC. Risk: ARP spoofing (man-in-the-middle).",
     "arp,data-link", 1),
    ("How does DHCP assign an IP address?",
     "DORA over UDP (client port 68, server port 67):\n"
     "- Discover: client broadcasts\n"
     "- Offer: server offers an IP\n"
     "- Request: client requests that IP\n"
     "- Acknowledge: server confirms\n"
     "The lease also carries the subnet mask, default gateway, DNS servers and lease time.",
     "dhcp,application", 1),
    ("MAC address vs IP address?",
     "- MAC: 48-bit hardware address burned into the NIC; flat; used for delivery within a LAN (Layer 2); changes hop by hop in frames\n"
     "- IP: logical, hierarchical address assigned by network config/DHCP; used for routing across networks (Layer 3); stays the same end to end (except with NAT)",
     "addressing", 1),
    ("Distance vector vs link state routing?",
     "- Distance vector (RIP): each router shares its whole table with neighbours only; Bellman-Ford; slow convergence and the count-to-infinity problem "
     "(fixes: split horizon, poison reverse, max 15 hops in RIP)\n"
     "- Link state (OSPF): each router floods its link info to all routers, builds the full topology and runs Dijkstra; fast convergence, more CPU/memory\n"
     "BGP (path vector) routes between autonomous systems.",
     "routing", 2),
    ("CSMA/CD vs CSMA/CA?",
     "- CSMA/CD (classic wired Ethernet): listen before sending, detect collisions while sending, then jam and use exponential backoff\n"
     "- CSMA/CA (Wi-Fi): collisions can't be detected reliably on wireless, so it avoids them with random backoff, ACKs and optional RTS/CTS (hidden terminal problem)\n"
     "Modern full-duplex switched Ethernet has no collisions.",
     "mac-protocols", 2),
    ("Which well-known ports should you know?",
     "20/21 FTP, 22 SSH, 23 Telnet, 25 SMTP, 53 DNS, 67/68 DHCP, 80 HTTP, 110 POP3, 143 IMAP, 443 HTTPS, 3306 MySQL, 5432 PostgreSQL.\n"
     "Well-known: 0-1023; registered: 1024-49151; dynamic/ephemeral: 49152-65535.",
     "ports", 1),
    ("What is a socket?",
     "An endpoint for communication, identified by IP + port + protocol. A TCP connection is uniquely identified by the 4-tuple "
     "(src IP, src port, dst IP, dst port).\n"
     "Server flow: socket -> bind -> listen -> accept. Client flow: socket -> connect. Then both send/recv.",
     "sockets,transport", 1),
    ("What is ICMP? How do ping and traceroute work?",
     "ICMP is the network-layer protocol for errors and diagnostics.\n"
     "- ping: sends ICMP Echo Request and gets Echo Reply; measures reachability and RTT\n"
     "- traceroute: sends packets with TTL = 1, 2, 3...; each router that drops one at TTL 0 returns ICMP Time Exceeded, revealing the path",
     "icmp,diagnostics", 2),
    ("How are transmission errors detected and corrected?",
     "Detection:\n"
     "- Parity bit: catches odd numbers of bit errors\n"
     "- Checksum: used by IP/TCP/UDP\n"
     "- CRC: polynomial division; catches burst errors; used by Ethernet\n"
     "Correction: Hamming code (single-bit correction), FEC. On the Internet, errors are usually detected and the data retransmitted.",
     "data-link,error-detection", 2),
    ("Bandwidth vs latency vs throughput?",
     "- Bandwidth: the maximum data rate of a link (bits per second)\n"
     "- Latency: the delay for one bit to travel end to end (propagation + transmission + queuing + processing); RTT is the round trip\n"
     "- Throughput: the data rate actually achieved, at most the bandwidth\n"
     "Bandwidth-delay product = the amount of data 'in flight' needed to fill the pipe.",
     "performance", 1),
    ("Unicast vs broadcast vs multicast vs anycast?",
     "- Unicast: one to one\n"
     "- Broadcast: one to all on the network segment (ARP request, DHCP Discover)\n"
     "- Multicast: one to a subscribed group (IPTV, 224.0.0.0/4)\n"
     "- Anycast: one to the nearest of many nodes sharing an address (root DNS servers, CDNs)",
     "addressing", 1),
    ("Forward proxy vs reverse proxy vs load balancer?",
     "- Forward proxy: sits in front of clients and makes requests for them (filtering, caching, anonymity)\n"
     "- Reverse proxy: sits in front of servers (Nginx) and handles TLS termination, caching, compression; hides the backends\n"
     "- Load balancer: a reverse proxy that spreads traffic across servers (round robin, least connections, IP hash); L4 (TCP) or L7 (HTTP)",
     "proxy,load-balancer", 2),
    ("What is a CDN?",
     "A Content Delivery Network: geographically distributed edge servers that cache static (and some dynamic) content close to users.\n"
     "Benefits: lower latency, less load on the origin, DDoS absorption. Users are routed to the nearest edge via DNS or anycast.",
     "cdn,performance", 1),
    ("WebSockets vs HTTP polling?",
     "- Short polling: the client asks repeatedly; simple but wasteful\n"
     "- Long polling: the server holds the request open until data arrives\n"
     "- SSE: a one-way server-to-client stream over HTTP\n"
     "- WebSocket: starts as an HTTP Upgrade, then a full-duplex persistent TCP connection; low overhead; used for chat, live feeds, games",
     "websockets,http", 2),
    ("What are the principles of REST?",
     "- Client-server, stateless (each request carries all its context)\n"
     "- Resources identified by URIs and manipulated with standard HTTP methods\n"
     "- Representations (JSON) and proper status codes\n"
     "- Cacheable responses, layered system, uniform interface",
     "rest,http", 2),
    ("Circuit switching vs packet switching?",
     "- Circuit switching: a dedicated path is reserved for the whole call (old telephone network); guaranteed bandwidth but idle capacity is wasted\n"
     "- Packet switching: data is split into packets routed independently over shared links (the Internet); efficient and robust, "
     "but has variable delay and possible loss",
     "switching", 1),
    ("SMTP vs POP3 vs IMAP?",
     "- SMTP (25/587): sends and relays mail between servers (push)\n"
     "- POP3 (110): downloads mail to one device, usually deleting it from the server\n"
     "- IMAP (143): keeps mail on the server and syncs folders and read state across devices",
     "email,application", 1),
]

OOP = [
    ("What are the four pillars of OOP?",
     "- Encapsulation: bundle data with the methods that use it and restrict direct access\n"
     "- Abstraction: expose what an object does, hide how it does it\n"
     "- Inheritance: a class acquires the properties/behaviour of another (code reuse, is-a)\n"
     "- Polymorphism: one interface, many forms (overloading, overriding)",
     "pillars", 1),
    ("Class vs object?",
     "A class is a blueprint/template defining data members and methods; it takes no memory for instance data by itself.\n"
     "An object is an instance of a class with its own state in memory. One class can create many objects.",
     "basics", 1),
    ("Encapsulation vs abstraction?",
     "- Encapsulation is about hiding data: private fields plus getters/setters, and controlling access (implementation-level)\n"
     "- Abstraction is about hiding complexity: showing only essential behaviour through abstract classes/interfaces (design-level)\n"
     "Example: a car exposes drive() (abstraction); engine internals are private (encapsulation).",
     "encapsulation,abstraction", 1),
    ("Compile-time vs runtime polymorphism?",
     "- Compile-time (static, early binding): function overloading, operator overloading, templates; resolved by the compiler\n"
     "- Runtime (dynamic, late binding): method overriding through a base-class pointer/reference; resolved at run time via the vtable (C++ virtual) "
     "or dynamic dispatch (Java, where non-static, non-final, non-private methods are virtual by default)",
     "polymorphism", 1),
    ("Method overloading vs overriding?",
     "- Overloading: same name, different parameter list (number/type/order), in the same class; compile-time; return type alone isn't enough\n"
     "- Overriding: subclass redefines a base method with the same signature; runtime; needs inheritance (virtual in C++); "
     "the override can't reduce visibility and may use a covariant return type",
     "polymorphism,overloading,overriding", 1),
    ("Can you overload by return type? Can static methods be overridden in Java?",
     "- Overloading by return type only: no; the call would be ambiguous, so it's a compile error\n"
     "- Static methods can't be overridden; a same-signature static method in a subclass hides the parent's (method hiding), "
     "and the call is resolved by the reference type at compile time\n"
     "- Private and final methods can't be overridden either",
     "polymorphism,java", 2),
    ("Abstract class vs interface (Java)?",
     "- Abstract class: can have state (fields), constructors, concrete and abstract methods, any access modifier; a class extends only one\n"
     "- Interface: a contract; fields are public static final; methods abstract by default, plus default/static (Java 8) and private (Java 9) methods; "
     "a class can implement many\n"
     "Use an abstract class for shared base code (is-a), an interface for a capability (can-do).",
     "abstraction,interface,java", 2),
    ("How do virtual functions work (vtable and vptr)?",
     "Every class with virtual functions has a vtable: an array of pointers to its most-derived implementations.\n"
     "Each object carries a hidden vptr pointing to its class's vtable, set by the constructor.\n"
     "A call through a base pointer/reference looks up the function in the vtable at run time, giving dynamic dispatch. "
     "Cost: one extra pointer per object and an indirect call.",
     "cpp,virtual,vtable", 2),
    ("What is a pure virtual function?",
     "A virtual function with no implementation in the base class, declared as virtual void f() = 0;\n"
     "A class with at least one pure virtual function is abstract: it can't be instantiated, and derived classes must override it to be concrete.\n"
     "(A pure virtual function may still have a definition, which is mainly useful for pure virtual destructors.)",
     "cpp,virtual,abstraction", 1),
    ("Why should a base class have a virtual destructor?",
     "When a derived object is deleted through a base pointer (Base* p = new Derived; delete p;), a non-virtual destructor calls "
     "only ~Base(). That is undefined behaviour and in practice leaks the derived part's resources.\n"
     "With a virtual destructor, ~Derived() runs first, then ~Base(). Rule: any class meant for polymorphic use needs a virtual destructor.",
     "cpp,virtual,destructor", 2),
    ("Can a constructor be virtual? What if a constructor calls a virtual function?",
     "No: virtual dispatch needs the vptr, which the constructor itself sets up, and to construct an object you must already know its exact type "
     "(use the factory / virtual clone() idiom instead).\n"
     "A virtual call inside a constructor or destructor resolves to the current class's version, not the derived override, "
     "because the derived part isn't built yet (or is already destroyed).",
     "cpp,virtual,constructor", 3),
    ("What is the diamond problem and how does C++ solve it?",
     "B and C both inherit from A, and D inherits from B and C. D then gets two copies of A, so a call to an A member is ambiguous.\n"
     "C++ fixes it with virtual inheritance (class B : virtual public A), so there is one shared A subobject; "
     "the most-derived class constructs A.\n"
     "Java avoids it by allowing single class inheritance (default-method conflicts in interfaces must be overridden explicitly).",
     "inheritance,diamond,cpp", 2),
    ("Why doesn't Java support multiple inheritance of classes?",
     "To avoid the diamond problem and ambiguity about which parent's state or implementation to use, keeping the language simpler.\n"
     "Java allows multiple inheritance of type through interfaces. If two interfaces provide the same default method, "
     "the class must override it (and can call X.super.method()).",
     "inheritance,java", 1),
    ("What types of inheritance are there?",
     "- Single: B extends A\n"
     "- Multilevel: C extends B extends A\n"
     "- Hierarchical: B and C both extend A\n"
     "- Multiple: C extends A and B (C++; in Java only through interfaces)\n"
     "- Hybrid: a combination of these (can create a diamond)",
     "inheritance", 1),
    ("Composition vs inheritance? Why 'favour composition'?",
     "Inheritance is an is-a relationship: tight coupling, fixed at compile time, and base-class changes ripple down (fragile base class).\n"
     "Composition is a has-a relationship: build behaviour from contained objects; looser coupling, can be swapped at run time, easier to test.\n"
     "Use inheritance only for a true is-a with a substitutable subtype (LSP); otherwise compose.",
     "composition,inheritance,design", 2),
    ("Association vs aggregation vs composition?",
     "- Association: a general 'uses/knows' relationship between independent objects (Teacher - Student)\n"
     "- Aggregation: a weak has-a; the part can exist without the whole (Department has Professors)\n"
     "- Composition: a strong has-a; the part's lifetime is bound to the whole (House has Rooms; delete the house and the rooms go too)",
     "association,composition", 2),
    ("What are the access modifiers in C++ and Java?",
     "C++: private (class only, the default for class), protected (class + derived), public (everyone; default for struct). friend grants access.\n"
     "Java: private (class), default/package-private (same package), protected (package + subclasses), public (everyone).",
     "access-modifiers", 1),
    ("What types of constructors does C++ have? Why is the copy constructor's parameter a reference?",
     "Default, parameterized, copy (T(const T&)), move (T(T&&)), and delegating constructors.\n"
     "If the copy constructor took its argument by value, passing it would itself need a copy, which calls the copy constructor again: infinite recursion. "
     "So it takes a reference; const allows copying from temporaries and const objects.",
     "cpp,constructor", 2),
    ("Shallow copy vs deep copy?",
     "- Shallow copy: copies member values as they are; pointer members end up pointing to the same memory, "
     "causing double free and shared mutations (this is the default copy constructor)\n"
     "- Deep copy: allocates new memory and copies the pointed-to data, so the objects are independent\n"
     "Needed whenever a class owns resources (raw pointers, file handles).",
     "copy,cpp", 2),
    ("What are the Rule of Three, Five and Zero (C++)?",
     "- Rule of Three: if a class needs a custom destructor, copy constructor or copy assignment, it probably needs all three (it manages a resource)\n"
     "- Rule of Five: add the move constructor and move assignment (C++11)\n"
     "- Rule of Zero: prefer RAII members (std::vector, std::unique_ptr) so you write none of them",
     "cpp,raii", 3),
    ("What are 'this' and 'super'?",
     "- this: a reference (Java) / pointer (C++) to the current object; used to separate fields from parameters, chain calls, "
     "pass the object along, and call another constructor (this(...) in Java)\n"
     "- super (Java): refers to the parent; super(...) calls the parent constructor (must be the first statement) and super.method() calls the overridden version. "
     "C++ uses Base::method() instead.",
     "basics,java,cpp", 1),
    ("What does the static keyword mean for members?",
     "- Static data member: one copy shared by all objects (class-level), e.g. an instance counter\n"
     "- Static method: called on the class, has no this, can access only static members directly\n"
     "- Static block (Java): runs once when the class loads\n"
     "In C/C++, a static local variable keeps its value between calls.",
     "static", 1),
    ("What does final mean in Java?",
     "- final variable: assigned once (a constant reference; the object it points to can still change)\n"
     "- final method: can't be overridden\n"
     "- final class: can't be extended (e.g. String)\n"
     "Related: finally is the always-run block in exception handling; finalize() is a deprecated GC hook.",
     "java,final", 1),
    ("What is a friend function in C++?",
     "A non-member function (or class) declared with friend inside a class, which gives it access to the class's private and protected members.\n"
     "Commonly used for operator<< / operator>> overloads and symmetric binary operators.\n"
     "Friendship is not inherited, not transitive and not mutual. It weakens encapsulation, so use it sparingly.",
     "cpp,friend", 2),
    ("Early binding vs late binding?",
     "- Early (static) binding: the call is resolved at compile time; used for non-virtual, static, private and overloaded methods; faster\n"
     "- Late (dynamic) binding: resolved at run time from the actual object type; used for virtual/overridden methods; enables runtime polymorphism",
     "polymorphism,binding", 1),
    ("Operator overloading: which C++ operators can't be overloaded?",
     "Most operators can be overloaded as member or friend functions (e.g. +, ==, <<, [], ()).\n"
     "Cannot be overloaded: :: (scope), . (member access), .* (pointer-to-member), ?: (ternary), sizeof, typeid, alignof.\n"
     "You can't change precedence, associativity or arity, or create new operators.",
     "cpp,operator-overloading", 2),
    ("Single Responsibility Principle (S in SOLID)?",
     "A class should have only one reason to change, meaning one responsibility.\n"
     "Example: split an Invoice class that calculates totals, prints and saves to the DB into Invoice, InvoicePrinter and InvoiceRepository.\n"
     "Gives smaller, testable, cohesive classes.",
     "solid,srp", 2),
    ("Open/Closed Principle (O in SOLID)?",
     "Software entities should be open for extension but closed for modification.\n"
     "Add new behaviour by adding new code (subclasses, strategies, plugins), not by editing working code.\n"
     "Example: instead of a switch on shape type in area(), let each Shape implement area(), so adding Triangle touches no existing class.",
     "solid,ocp", 2),
    ("Liskov Substitution Principle (L in SOLID)?",
     "Objects of a subclass must be usable wherever the base class is expected, without breaking correctness.\n"
     "A subclass must not strengthen preconditions, weaken postconditions or throw unexpected exceptions.\n"
     "Classic violation: Square extends Rectangle; setting the width also changes the height, breaking code that expects them independent.",
     "solid,lsp", 2),
    ("Interface Segregation Principle (I in SOLID)?",
     "Clients shouldn't be forced to depend on methods they don't use. Prefer several small, role-specific interfaces to one fat interface.\n"
     "Example: split IMachine { print(); scan(); fax(); } into IPrinter, IScanner, IFax, so a basic printer doesn't implement fax() by throwing an exception.",
     "solid,isp", 2),
    ("Dependency Inversion Principle (D in SOLID)?",
     "High-level modules shouldn't depend on low-level modules; both should depend on abstractions. Abstractions shouldn't depend on details.\n"
     "Example: OrderService depends on a PaymentGateway interface, not on StripeClient; the concrete class is injected (dependency injection).\n"
     "Gives swappable implementations and easy mocking in tests.",
     "solid,dip", 2),
    ("Singleton pattern: how do you make it thread-safe?",
     "Ensures a class has exactly one instance with a global access point: private constructor, static getInstance().\n"
     "Thread-safe options:\n"
     "- Eager initialization\n"
     "- Double-checked locking with a volatile instance (Java)\n"
     "- Bill Pugh static holder class, or an enum singleton (Java)\n"
     "- Meyers singleton in C++11: static local in getInstance() (initialization is thread-safe)\n"
     "Downsides: global state, hard to test.",
     "design-patterns,singleton", 2),
    ("Explain the Factory pattern.",
     "A creational pattern: object creation goes through a factory method instead of calling new directly, so the client depends on an interface.\n"
     "Example: ShapeFactory.create(\"circle\") returns a Shape.\n"
     "Factory Method: subclasses decide which class to instantiate. Abstract Factory: creates families of related objects (e.g. a UI kit per OS).",
     "design-patterns,factory", 2),
    ("Explain the Observer pattern.",
     "A behavioural pattern: a subject keeps a list of observers and notifies them automatically when its state changes (one-to-many, publish-subscribe).\n"
     "Examples: event listeners, YouTube subscribers, MVC model -> views.\n"
     "Gives loose coupling. Watch out for memory leaks from observers that never unsubscribe.",
     "design-patterns,observer", 2),
    ("Explain the Strategy pattern.",
     "A behavioural pattern: define a family of interchangeable algorithms behind one interface and choose one at run time.\n"
     "Example: PaymentStrategy with CardPayment and UpiPayment; Checkout holds a strategy and calls pay().\n"
     "Replaces big if/else or switch blocks and follows the Open/Closed Principle (composition over inheritance).",
     "design-patterns,strategy", 2),
    ("Adapter vs Decorator pattern?",
     "Both are structural wrappers.\n"
     "- Adapter: converts one interface into another that the client expects (e.g. a legacy XML API wrapped to look like a JSON interface)\n"
     "- Decorator: keeps the same interface and adds behaviour dynamically by wrapping (e.g. Java's BufferedInputStream(new FileInputStream(...)))",
     "design-patterns,adapter,decorator", 3),
    ("What are the three categories of design patterns?",
     "- Creational (how objects are created): Singleton, Factory, Abstract Factory, Builder, Prototype\n"
     "- Structural (how objects are composed): Adapter, Decorator, Facade, Proxy, Composite\n"
     "- Behavioural (how objects interact): Observer, Strategy, Command, Iterator, State, Template Method",
     "design-patterns", 1),
    ("Coupling vs cohesion?",
     "- Coupling: how much one module depends on another; aim for low coupling (interfaces, DI)\n"
     "- Cohesion: how closely the responsibilities within one module are related; aim for high cohesion (SRP)\n"
     "Low coupling with high cohesion gives code that is easy to change, test and reuse.",
     "design", 1),
    ("Checked vs unchecked exceptions in Java?",
     "- Checked: subclasses of Exception (not RuntimeException), checked at compile time; you must catch or declare them with throws (IOException, SQLException)\n"
     "- Unchecked: RuntimeException and its subclasses (NullPointerException, ArithmeticException) and Errors; not enforced by the compiler\n"
     "Error (OutOfMemoryError) means a serious problem that apps usually shouldn't catch.",
     "java,exceptions", 2),
    ("What is object slicing in C++?",
     "Assigning or passing a derived object by value as a base type copies only the base part; the derived members and overriding behaviour are 'sliced off'.\n"
     "Example: void f(Base b); f(derived); calls Base's version of virtual functions inside f.\n"
     "Avoid it by passing by reference or pointer (const Base&).",
     "cpp,polymorphism", 3),
    ("new/delete vs malloc/free?",
     "- new is an operator: allocates and calls the constructor, returns a typed pointer, throws std::bad_alloc on failure, can be overloaded\n"
     "- malloc is a function: raw bytes only, no constructor, returns void* (cast needed in C++), returns NULL on failure\n"
     "Pair them correctly: new/delete, new[]/delete[], malloc/free. Prefer smart pointers in modern C++.",
     "cpp,memory", 2),
    ("struct vs class in C++?",
     "They are nearly identical. The only differences are defaults: struct members and base classes are public by default, class ones are private.\n"
     "By convention, struct is used for plain data aggregates and class for types with invariants and behaviour.\n"
     "(In C, a struct can't have member functions or access control.)",
     "cpp,basics", 1),
    ("Templates (C++) vs generics (Java)?",
     "- C++ templates: compile-time code generation; a separate instantiation per type (code bloat possible); work with primitives; enable metaprogramming\n"
     "- Java generics: type erasure; one compiled class, type info removed at run time; no primitives (boxing); compile-time type safety only",
     "generics,templates", 2),
]

SQL = [
    ("How do you find the Nth highest salary?",
     "- LIMIT/OFFSET: SELECT DISTINCT salary FROM Employee ORDER BY salary DESC LIMIT 1 OFFSET N-1;\n"
     "- Window: SELECT salary FROM (SELECT salary, DENSE_RANK() OVER (ORDER BY salary DESC) r FROM Employee) t WHERE r = N LIMIT 1;\n"
     "- Correlated: SELECT DISTINCT salary FROM Employee e1 WHERE N-1 = (SELECT COUNT(DISTINCT salary) FROM Employee e2 WHERE e2.salary > e1.salary);\n"
     "Use DISTINCT/DENSE_RANK so duplicate salaries are handled.",
     "nth-salary,window", 2),
    ("Second highest salary without LIMIT or window functions?",
     "SELECT MAX(salary) FROM Employee WHERE salary < (SELECT MAX(salary) FROM Employee);\n"
     "It returns NULL when no second value exists, which LeetCode expects. Handles duplicates of the top salary.",
     "nth-salary,subquery", 1),
    ("WHERE vs HAVING?",
     "- WHERE filters rows before grouping and can't use aggregates\n"
     "- HAVING filters groups after GROUP BY and can use aggregates\n"
     "Example: SELECT dept, COUNT(*) FROM emp WHERE active = 1 GROUP BY dept HAVING COUNT(*) > 5;\n"
     "Filter in WHERE when you can; it's cheaper.",
     "group-by,having", 1),
    ("What is the logical execution order of a SELECT?",
     "FROM / JOIN -> WHERE -> GROUP BY -> HAVING -> SELECT (window functions run here) -> DISTINCT -> ORDER BY -> LIMIT/OFFSET.\n"
     "That's why a SELECT alias can't be used in WHERE but can be used in ORDER BY (MySQL also allows it in HAVING).",
     "query-order", 2),
    ("Explain the SQL join types.",
     "- INNER JOIN: only matching rows from both sides\n"
     "- LEFT (OUTER) JOIN: all left rows, with NULLs where the right has no match\n"
     "- RIGHT JOIN: the mirror of LEFT\n"
     "- FULL OUTER JOIN: all rows from both sides (MySQL lacks it; use LEFT UNION RIGHT)\n"
     "- CROSS JOIN: Cartesian product (m x n rows)\n"
     "- SELF JOIN: a table joined with itself using aliases",
     "joins", 1),
    ("Find employees who earn more than their managers.",
     "Self join:\n"
     "SELECT e.name FROM Employee e JOIN Employee m ON e.manager_id = m.id WHERE e.salary > m.salary;\n"
     "e is the employee row and m is the same table viewed as the manager.",
     "joins,self-join", 2),
    ("How do you find and delete duplicate rows?",
     "Find: SELECT email, COUNT(*) FROM Person GROUP BY email HAVING COUNT(*) > 1;\n"
     "Delete, keeping the lowest id:\n"
     "- DELETE p1 FROM Person p1 JOIN Person p2 ON p1.email = p2.email AND p1.id > p2.id; (MySQL)\n"
     "- Or with a CTE: ROW_NUMBER() OVER (PARTITION BY email ORDER BY id) and delete where rn > 1",
     "duplicates,group-by", 2),
    ("ROW_NUMBER vs RANK vs DENSE_RANK?",
     "For salaries 100, 100, 90 ordered descending:\n"
     "- ROW_NUMBER: 1, 2, 3 (always unique)\n"
     "- RANK: 1, 1, 3 (ties share a rank, then a gap)\n"
     "- DENSE_RANK: 1, 1, 2 (ties share a rank, no gap)\n"
     "Use DENSE_RANK for 'Nth highest distinct value' questions.",
     "window,ranking", 2),
    ("Window functions vs GROUP BY? Write a running total.",
     "GROUP BY collapses rows into one row per group. A window function (aggregate OVER (...)) computes across related rows but keeps every row.\n"
     "Running total: SELECT day, amount, SUM(amount) OVER (ORDER BY day) AS running FROM sales;\n"
     "Per group: OVER (PARTITION BY user_id ORDER BY day). Frame clause: ROWS BETWEEN 6 PRECEDING AND CURRENT ROW for a 7-day moving sum.",
     "window,running-total", 2),
    ("Find the top earner (or top 3) in each department.",
     "WITH r AS (\n"
     "  SELECT d.name dept, e.name, e.salary,\n"
     "         DENSE_RANK() OVER (PARTITION BY e.dept_id ORDER BY e.salary DESC) rk\n"
     "  FROM Employee e JOIN Department d ON e.dept_id = d.id)\n"
     "SELECT dept, name, salary FROM r WHERE rk <= 3;  -- rk = 1 for the top earner(s)\n"
     "Without windows: WHERE (dept_id, salary) IN (SELECT dept_id, MAX(salary) FROM Employee GROUP BY dept_id).",
     "window,top-n", 3),
    ("EXISTS vs IN? What is the NOT IN NULL trap?",
     "- IN compares a value to a list or subquery result; good for small lists\n"
     "- EXISTS stops at the first matching row of a correlated subquery; good when the outer table is small and the inner table is indexed\n"
     "Modern optimizers often turn both into the same semi-join.\n"
     "Trap: x NOT IN (subquery) returns no rows if the subquery yields any NULL. Use NOT EXISTS (NULL-safe) instead.",
     "subquery,exists", 2),
    ("UNION vs UNION ALL?",
     "- UNION: combines results and removes duplicates (an extra sort/hash step, so slower)\n"
     "- UNION ALL: keeps all rows including duplicates; faster\n"
     "Both need the same number of columns with compatible types; column names come from the first SELECT.",
     "set-operations", 1),
    ("COUNT(*) vs COUNT(col) vs COUNT(DISTINCT col)?",
     "- COUNT(*): counts all rows, including NULLs\n"
     "- COUNT(col): counts rows where col IS NOT NULL\n"
     "- COUNT(DISTINCT col): counts unique non-NULL values\n"
     "COUNT(1) behaves the same as COUNT(*).",
     "aggregates", 1),
    ("How does NULL behave in SQL?",
     "- NULL means unknown; any comparison with NULL (even NULL = NULL) gives UNKNOWN, so use IS NULL / IS NOT NULL\n"
     "- Aggregates (SUM, AVG, MAX) ignore NULLs; AVG divides by the non-NULL count\n"
     "- COALESCE(a, b, ...) returns the first non-NULL value; IFNULL/ISNULL/NVL are vendor variants\n"
     "- GROUP BY puts all NULLs in one group",
     "null", 1),
    ("Correlated vs non-correlated subquery?",
     "- Non-correlated: independent of the outer query; runs once (e.g. WHERE salary > (SELECT AVG(salary) FROM emp))\n"
     "- Correlated: references outer columns, so it is logically re-evaluated per outer row "
     "(e.g. salary above the average of the employee's own department: WHERE e.salary > (SELECT AVG(salary) FROM emp x WHERE x.dept = e.dept))\n"
     "Correlated subqueries are often rewritten as joins or window functions for speed.",
     "subquery", 2),
    ("What is a CTE? Show a recursive CTE.",
     "A Common Table Expression (WITH name AS (...)) is a named temporary result set that improves readability and can be referenced several times.\n"
     "Recursive (org chart / numbers):\n"
     "WITH RECURSIVE nums(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM nums WHERE n < 10) SELECT n FROM nums;\n"
     "It has an anchor member, a recursive member and a termination condition.",
     "cte,recursive", 2),
    ("Use LAG/LEAD: find days warmer than the previous day.",
     "LAG(col, k) reads the value k rows before; LEAD reads k rows after (within the window order).\n"
     "SELECT id FROM (SELECT id, recordDate, temperature, LAG(temperature) OVER (ORDER BY recordDate) prev_t, "
     "LAG(recordDate) OVER (ORDER BY recordDate) prev_d FROM Weather) t\n"
     "WHERE temperature > prev_t AND recordDate = prev_d + INTERVAL 1 DAY;  -- MySQL date syntax\n"
     "Or use a self join on DATEDIFF(w1.recordDate, w2.recordDate) = 1.",
     "window,lag-lead", 3),
    ("Find customers who never placed an order.",
     "- Anti-join: SELECT c.name FROM Customers c LEFT JOIN Orders o ON o.customer_id = c.id WHERE o.id IS NULL;\n"
     "- Or: SELECT name FROM Customers c WHERE NOT EXISTS (SELECT 1 FROM Orders o WHERE o.customer_id = c.id);\n"
     "Avoid NOT IN if Orders.customer_id can be NULL.",
     "joins,anti-join", 1),
    ("CHAR vs VARCHAR?",
     "- CHAR(n): fixed length, padded with spaces; slightly faster for truly fixed-size values (country codes, flags)\n"
     "- VARCHAR(n): variable length up to n, stores only the actual length (plus 1-2 bytes for the length); saves space for varying text\n"
     "TEXT/CLOB is for large strings.",
     "data-types", 1),
    ("How do you pivot rows into columns (conditional aggregation)?",
     "Use CASE inside aggregates:\n"
     "SELECT student,\n"
     "  SUM(CASE WHEN subject = 'Math' THEN marks ELSE 0 END) AS math,\n"
     "  SUM(CASE WHEN subject = 'Physics' THEN marks ELSE 0 END) AS physics\n"
     "FROM Marks GROUP BY student;\n"
     "Also handy for counts: SUM(status = 'done') in MySQL, or COUNT(*) FILTER (WHERE ...) in Postgres.",
     "pivot,case", 2),
    ("What SQL constraints are there?",
     "- NOT NULL: a value is required\n"
     "- UNIQUE: no duplicate values (NULLs are usually allowed)\n"
     "- PRIMARY KEY: UNIQUE + NOT NULL, one per table\n"
     "- FOREIGN KEY: must match a referenced key; ON DELETE CASCADE / SET NULL / RESTRICT\n"
     "- CHECK: a boolean condition (e.g. CHECK (age >= 18))\n"
     "- DEFAULT: the value used when none is given",
     "constraints", 1),
]

SUBJECT_ROWS = {"OS": OS, "DBMS": DBMS, "CN": CN, "OOP": OOP, "SQL": SQL}

DECK = [
    {"subject": subject, "question": q, "answer": a, "tags": tags, "difficulty": d}
    for subject, rows in SUBJECT_ROWS.items()
    for (q, a, tags, d) in rows
]
