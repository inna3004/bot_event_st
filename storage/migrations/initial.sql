create table answers (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    value VARCHAR(255) NOT NULL,
    question INT REFERENCES questions(id)
);


create table questions (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    text VARCHAR(255) NOT NULL,
    correct_answer_id integer,
    FOREIGN KEY (correct_answer_id) REFERENCES answers(id)
);


create table tests (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    title  VARCHAR(255) NOT NULL,
    difficult  integer,
    category VARCHAR(255) NOT NULL,
    question_id integer,
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

create table  results (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    score integer,
    user_id integer,
    test_id integer,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (test_id) REFERENCES tests(id)
);

create table  users (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    is_admin BOOLEAN;