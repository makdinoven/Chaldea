import { useState, useEffect } from 'react';

import ClassItem from './ClassItem/ClassItem';

import styles from './ClassPage.module.scss';

export default function ClassPage({ classes, onSelectClass, selectedClassId }) {
  const [classIndex, setClassIndex] = useState(selectedClassId);

  const handleClick = (index) => {
    setClassIndex(index);
    onSelectClass(index);
  };

  return (
    <div className={styles.classes_container}>
      {classes.map((classData) => (
        <ClassItem
          onClick={() => handleClick(classData.id)}
          key={classData.id}
          data={classData}
          index={classData.id}
          currentIndex={classIndex}
          setCurrentIndex={setClassIndex}
        />
      ))}
    </div>
  );
}
