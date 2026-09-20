// Разделы «Руководства». Слаг раздела = значение ENUM `game_rules.section`
// в БД и Pydantic-литерала на бэкенде, а также сегмент URL `/guide/:section`.
// Единый словарь без таблиц соответствия.

export type GuideSection = 'site' | 'roleplay' | 'technobook';

export interface GuideSectionMeta {
  slug: GuideSection;
  label: string;
  description: string;
}

export const GUIDE_SECTIONS: GuideSectionMeta[] = [
  {
    slug: 'site',
    label: 'Правила сайта',
    description: 'Общие правила поведения и работы с сайтом.',
  },
  {
    slug: 'roleplay',
    label: 'Правила ролевой',
    description: 'Как устроена игра и что можно в отыгрыше.',
  },
  {
    slug: 'technobook',
    label: 'Технобук',
    description: 'Технические материалы и справочник по механикам.',
  },
];

export const isGuideSection = (value: string | undefined | null): value is GuideSection =>
  GUIDE_SECTIONS.some((section) => section.slug === value);
