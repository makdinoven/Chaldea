import { useState, useEffect } from 'react';

import Input from '../../CommonComponents/Input/Input';
import Select from '../../CommonComponents/Select/Select';
import Textarea from '../../CommonComponents/Textarea/Textarea';

import styles from './BiographyPage.module.css';

export default function BiographyPage({
  onFormValuesChange,
  enteredFormValues,
}) {
  const [formValues, setFormValues] = useState({
    biography: enteredFormValues.biography,
    personality: enteredFormValues.personality,
    appearance: enteredFormValues.appearance,
    name: enteredFormValues.name,
    age: enteredFormValues.age,
    height: enteredFormValues.height,
    weight: enteredFormValues.weight,
    background: enteredFormValues.background,
    sex: enteredFormValues.sex,
  });

  useEffect(() => {
    onFormValuesChange(formValues);
  }, [formValues, onFormValuesChange]);

  const handleInputChange = (e) => {
    const { id, value } = e.target;
    setFormValues((prevValues) => ({
      ...prevValues,
      [id]: value,
    }));
  };

  const handleSelectChange = (e) => {
    const { value } = e.target;
    setFormValues((prevValues) => ({
      ...prevValues,
      sex: value,
    }));
  };

  const handleTextareaChange = (e) => {
    const { id, value } = e.target;
    setFormValues((prevValues) => ({
      ...prevValues,
      [id]: value,
    }));
  };

  const inputsData = [
    { id: 'name', isRequired: true, text: 'Имя персонажа*', maxLength: 20 },
    { id: 'age', text: 'Возраст', type: 'number' },
    { id: 'weight', text: 'Вес', type: 'number' },
    { id: 'background', text: 'Происхождение', maxLength: 20 },
    { id: 'height', text: 'Рост', type: 'number' },
  ];

  const selectOptions = [
    { name: 'Пол', value: '', isDisabled: true },
    { name: 'Мужской', value: 'Мужской' },
    { name: 'Женский', value: 'Женский' },
    { name: 'Бесполый', value: 'Бесполый' },
  ];

  const textareasData = [
    { id: 'biography', text: 'Биография*', isRequired: true, link: '/rules' },
    { id: 'personality', text: 'Личность*', isRequired: true, link: '/rules' },
    { id: 'appearance', text: 'Внешность*', isRequired: true, link: '/rules' },
  ];

  return (
    <form className={styles.form} action=''>
      {textareasData.map((data, index) => (
        <Textarea
          key={index}
          id={data.id}
          text={data.text}
          link={data.link}
          isRequired={data.isRequired}
          value={formValues[data.id]}
          onChange={handleTextareaChange}
        />
      ))}

      <div className={styles.inputs_wrapper}>
        {inputsData.map((data, index) => (
          <Input
            isRequired={data.isRequired}
            key={index}
            id={data.id}
            type={data.type}
            maxLength={data.maxLength}
            text={data.text}
            value={formValues[data.id]}
            onChange={handleInputChange}
          />
        ))}
        <Select
          options={selectOptions}
          value={formValues.sex}
          onChange={handleSelectChange}
        />
      </div>
    </form>
  );
}
