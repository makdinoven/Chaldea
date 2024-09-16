import { useState, useEffect } from 'react';

import ClassButton from './ClassButton/ClassButton';

import styles from './ClassPage.module.css';

export default function ClassPage({ classes, onSelectClass, selectedClassId }) {
  const [classIndex, setClassIndex] = useState(selectedClassId);

  const handleContainerClick = (index) => {
    setClassIndex(index);
    onSelectClass(index);
  };

  return (
    <div className={styles.classes_container}>
      {classes.map((classData) => (
        <div
          key={classData.id}
          onClick={() => handleContainerClick(classData.id)}
          className={styles.class_container}
        >
          <img src={classData.img} alt='' />
          <ClassButton
            text={classData.name}
            index={classData.id}
            currentIndex={classIndex}
            setCurrentIndex={setClassIndex}
          />
        </div>
      ))}
    </div>
  );
}
